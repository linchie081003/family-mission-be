"""
Import data hasil export Firebase ke PostgreSQL (aplikasi Family Mission baru).

Jalankan dari folder new/backend:

  python migration/import_to_postgres.py

Prasyarat:
  - exported_config.json dan exported_logs.json ada di folder migration/
  - Database sudah jalan (docker compose up db -d)
  - Backend pernah di-start minimal sekali (schema + seed plan sudah ada)

CATATAN PIN anak:
  PIN lama tidak dipindahkan (versi baru pakai hash). Anak buat PIN baru saat login pertama.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import getpass
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.auth import generate_family_code, hash_password  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import async_session, engine  # noqa: E402
from app.core.tokens import utcnow  # noqa: E402
from app.models.models import (  # noqa: E402
    Child,
    CompletionStatus,
    Family,
    Goal,
    Mission,
    MissionCategory,
    MissionCompletion,
    MissionDifficulty,
    Parent,
    ParentRole,
    PointTransaction,
    Punishment,
    PunishmentRecord,
    RedemptionRequest,
    RedemptionStatus,
    RedemptionType,
    Reward,
    SettingsHistory,
    TransactionType,
)
from app.repositories.family_repository import FamilyRepository  # noqa: E402
from app.repositories.parent_repository import ParentRepository  # noqa: E402
from app.services.plan_presets import FAMILY_PRESET  # noqa: E402
from app.services.subscription_service import SubscriptionService  # noqa: E402

MIGRATION_DIR = Path(__file__).resolve().parent


def load_json(name: str) -> dict:
    path = MIGRATION_DIR / name
    if not path.exists():
        print(f"File {name} tidak ditemukan di {MIGRATION_DIR}")
        print("Jalankan dulu: python migration/export_from_firebase.py")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(value) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return date.today()


def parse_datetime_ms(value) -> datetime:
    try:
        ts = int(value) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError):
        return utcnow()


def date_to_completed_at(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(
        hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )


def map_category(raw: str | None) -> MissionCategory:
    value = (raw or "reguler").lower()
    if value in ("reguler", "regular"):
        return MissionCategory.REGULAR
    if value == "ibadah":
        return MissionCategory.IBADAH
    return MissionCategory.ADDITIONAL


def map_difficulty(raw: str | None) -> MissionDifficulty:
    value = (raw or "medium").lower()
    try:
        return MissionDifficulty(value)
    except ValueError:
        return MissionDifficulty.MEDIUM


def map_completion_status(raw: str | None) -> CompletionStatus:
    value = (raw or "approved").lower()
    if value == "rejected":
        return CompletionStatus.REJECTED
    if value == "pending":
        return CompletionStatus.PENDING
    return CompletionStatus.APPROVED


def log_sort_key(item: dict) -> tuple[int, str]:
    created = item.get("createdAt")
    if created is not None:
        try:
            return int(created), item.get("id", "")
        except (TypeError, ValueError):
            pass
    return int(parse_date(item.get("date")).strftime("%s")) * 1000, item.get("id", "")


def save_avatar_from_data_url(photo: str | None, child_id: int) -> str | None:
    if not photo or not photo.startswith("data:"):
        return None
    match = re.match(r"data:image/(\w+);base64,(.+)", photo, re.DOTALL)
    if not match:
        return None
    ext = match.group(1).lower()
    if ext == "jpeg":
        ext = "jpg"
    try:
        raw = base64.b64decode(match.group(2))
    except (ValueError, binascii.Error):
        return None
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"migrate_{child_id}_{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, "wb") as f:
        f.write(raw)
    return f"/uploads/{filename}"


def apply_transaction(
    db,
    child: Child,
    family: Family,
    transaction_type: TransactionType,
    points: int,
    description: str,
    reference_id: int | None,
    created_at: datetime,
    *,
    affects_lifetime: bool = True,
) -> PointTransaction:
    if affects_lifetime and points > 0:
        child.lifetime_points += points
    child.active_balance += points
    tx = PointTransaction(
        child_id=child.id,
        transaction_type=transaction_type,
        points=points,
        active_balance_after=child.active_balance,
        lifetime_points_after=child.lifetime_points,
        rupiah_per_point=family.rupiah_per_point,
        description=description[:300],
        reference_id=reference_id,
        created_at=created_at,
    )
    db.add(tx)
    return tx


async def generate_unique_family_code(families: FamilyRepository) -> str:
    code = generate_family_code()
    while await families.get_by_code(code):
        code = generate_family_code()
    return code


async def resolve_mission_id(
    log_item: dict,
    mission_id_map: dict[str, int],
    missions_by_title: dict[str, int],
) -> int | None:
    old_id = log_item.get("missionId")
    if old_id and old_id in mission_id_map:
        return mission_id_map[old_id]
    name = (log_item.get("missionName") or "").strip()
    if name in missions_by_title:
        return missions_by_title[name]
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import data Firebase ke PostgreSQL")
    parser.add_argument("--family-name", help="Nama keluarga")
    parser.add_argument("--parent-name", help="Nama orang tua")
    parser.add_argument("--email", help="Email login parent")
    parser.add_argument("--password", help="Password login parent (min 8 karakter)")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    config = load_json("exported_config.json")
    logs_data = load_json("exported_logs.json")
    log_items = sorted(logs_data.get("items") or [], key=log_sort_key)

    print("=== Migrasi Family Mission: Firebase -> PostgreSQL ===\n")
    print(
        f"Ditemukan: {len(config.get('children', []))} anak, "
        f"{len(config.get('missions', []))} misi, "
        f"{len(config.get('punishments', []))} punishment, "
        f"{len(config.get('rewards', []))} reward, "
        f"{len(log_items)} baris riwayat.\n"
    )

    family_name = (args.family_name or input("Nama keluarga: ").strip()) or "Keluarga Saya"
    parent_name = (args.parent_name or input("Nama orang tua: ").strip()) or "Admin"
    admin_email = (args.email or input("Email login parent: ").strip()).lower()
    if not admin_email:
        print("Email wajib diisi.")
        sys.exit(1)

    admin_password = args.password or getpass.getpass("Password login parent (min 8 karakter): ")
    while len(admin_password) < 8:
        print("Password minimal 8 karakter.")
        admin_password = getpass.getpass("Password: ")

    rupiah_per_point = int(config.get("pointValue") or 1000)
    daily_point_limit = int(config.get("dailyMax") or 50)
    min_cash_redemption = int((config.get("cashout") or {}).get("minPoints") or 100)

    async with async_session() as db:
        families = FamilyRepository(db)
        parents = ParentRepository(db)

        if await parents.email_exists(admin_email) or await families.email_exists(admin_email):
            print(f"Email {admin_email} sudah terdaftar. Gunakan email lain atau hapus data lama.")
            sys.exit(1)

        now = utcnow()
        password_hash = hash_password(admin_password)
        family = Family(
            email=admin_email,
            password_hash=password_hash,
            family_name=family_name,
            family_code=await generate_unique_family_code(families),
            referral_code=await families.generate_unique_referral_code(),
            rupiah_per_point=rupiah_per_point,
            daily_point_limit=daily_point_limit,
            min_cash_redemption=min_cash_redemption,
            is_active=True,
            activated_at=now,
            activation_preset="family",
            **FAMILY_PRESET,
        )
        db.add(family)
        await db.flush()

        parent = Parent(
            family_id=family.id,
            email=admin_email,
            password_hash=password_hash,
            name=parent_name,
            role=ParentRole.FATHER,
            is_primary=True,
            email_verified=True,
            terms_accepted_at=now,
            privacy_accepted_at=now,
            parental_consent_at=now,
            child_data_protection_accepted_at=now,
            legal_doc_version=settings.legal_doc_version,
        )
        db.add(parent)
        await db.flush()

        try:
            await SubscriptionService(db).start_trial(family, plan_slug="family", days=10)
        except Exception as exc:
            print(f"  Catatan: trial subscription dilewati ({exc}). Fitur family preset tetap aktif.")

        child_id_map: dict[str, int] = {}
        child_by_new_id: dict[int, Child] = {}
        for index, c in enumerate(config.get("children") or []):
            child = Child(
                family_id=family.id,
                name=c.get("name") or f"Anak {index + 1}",
                color=c.get("color") or "#6366f1",
                weekly_target=int(c.get("weeklyTarget") or 100),
                pin_hash=None,
            )
            db.add(child)
            await db.flush()

            avatar = save_avatar_from_data_url(c.get("photo"), child.id)
            if avatar:
                child.avatar_url = avatar

            goal = c.get("goal")
            if goal and goal.get("name"):
                db.add(
                    Goal(
                        child_id=child.id,
                        title=str(goal.get("name")),
                        target_points=int(goal.get("target") or 0),
                    )
                )

            old_id = c.get("id")
            if old_id:
                child_id_map[old_id] = child.id
            child_by_new_id[child.id] = child

        mission_id_map: dict[str, int] = {}
        missions_by_title: dict[str, int] = {}
        for index, m in enumerate(config.get("missions") or []):
            title = m.get("name") or f"Misi {index + 1}"
            emoji = m.get("emoji") or ""
            description = f"{emoji} {title}".strip() if emoji else None
            mission = Mission(
                family_id=family.id,
                title=title,
                description=description,
                category=map_category(m.get("category")),
                points=int(m.get("points") or 0),
                difficulty=map_difficulty(m.get("difficulty")),
                is_active=bool(m.get("active", True)),
                sort_order=index,
            )
            db.add(mission)
            await db.flush()
            old_id = m.get("id")
            if old_id:
                mission_id_map[old_id] = mission.id
            missions_by_title[title] = mission.id

        punishment_id_map: dict[str, int] = {}
        for p in config.get("punishments") or []:
            punishment = Punishment(
                family_id=family.id,
                title=p.get("name") or "Punishment",
                points_deducted=int(p.get("points") or 0),
                is_active=bool(p.get("active", True)),
            )
            db.add(punishment)
            await db.flush()
            old_id = p.get("id")
            if old_id:
                punishment_id_map[old_id] = punishment.id

        reward_id_map: dict[str, int] = {}
        for r in config.get("rewards") or []:
            emoji = r.get("emoji") or ""
            title = r.get("name") or "Reward"
            reward = Reward(
                family_id=family.id,
                title=title,
                description=f"{emoji} {title}".strip() if emoji else None,
                points_cost=int(r.get("cost") or 0),
                is_active=bool(r.get("active", True)),
            )
            db.add(reward)
            await db.flush()
            old_id = r.get("id")
            if old_id:
                reward_id_map[old_id] = reward.id

        skipped = 0
        for item in log_items:
            child_new_id = child_id_map.get(item.get("childId"))
            if not child_new_id:
                skipped += 1
                continue

            child = child_by_new_id[child_new_id]
            log_type = (item.get("type") or "mission").lower()
            status = map_completion_status(item.get("status"))
            created_at = parse_datetime_ms(item.get("createdAt")) if item.get("createdAt") else date_to_completed_at(parse_date(item.get("date")))
            points = int(item.get("points") or 0)
            label = item.get("missionName") or "-"

            if log_type in ("mission", "additional"):
                mission_id = await resolve_mission_id(item, mission_id_map, missions_by_title)
                if not mission_id:
                    skipped += 1
                    continue

                completion = MissionCompletion(
                    child_id=child.id,
                    mission_id=mission_id,
                    status=status,
                    points_awarded=points if status == CompletionStatus.APPROVED else 0,
                    completed_at=date_to_completed_at(parse_date(item.get("date"))),
                    reviewed_at=created_at if status != CompletionStatus.PENDING else None,
                )
                db.add(completion)
                await db.flush()

                if status == CompletionStatus.APPROVED and points != 0:
                    apply_transaction(
                        db,
                        child,
                        family,
                        TransactionType.MISSION,
                        points,
                        f"Misi: {label}",
                        completion.id,
                        created_at,
                    )
                    child.last_activity_date = created_at

            elif log_type == "punishment":
                punishment_id = punishment_id_map.get(item.get("missionId"))
                record = PunishmentRecord(
                    child_id=child.id,
                    punishment_id=punishment_id,
                    title=label,
                    points_deducted=abs(points),
                    created_at=created_at,
                )
                db.add(record)
                await db.flush()

                if status == CompletionStatus.APPROVED and points != 0:
                    apply_transaction(
                        db,
                        child,
                        family,
                        TransactionType.PUNISHMENT,
                        points,
                        f"Punishment: {label}",
                        record.id,
                        created_at,
                    )

            elif log_type in ("redeem", "cashout"):
                redemption_type = RedemptionType.REWARD if log_type == "redeem" else RedemptionType.CASH
                reward_id = reward_id_map.get(item.get("missionId")) if log_type == "redeem" else None
                redeem_points = abs(points)

                redemption = RedemptionRequest(
                    child_id=child.id,
                    redemption_type=redemption_type,
                    reward_id=reward_id,
                    points=redeem_points,
                    rupiah_per_point=family.rupiah_per_point,
                    status=RedemptionStatus(status.value),
                    created_at=created_at,
                    reviewed_at=created_at if status != RedemptionStatus.PENDING else None,
                )
                db.add(redemption)
                await db.flush()

                if status == RedemptionStatus.APPROVED and points != 0:
                    apply_transaction(
                        db,
                        child,
                        family,
                        TransactionType.REDEMPTION,
                        points,
                        label,
                        redemption.id,
                        created_at,
                        affects_lifetime=False,
                    )
                    child.total_redeemed += redeem_points

            else:
                skipped += 1

        running_settings = {
            "rupiah_per_point": rupiah_per_point,
            "daily_point_limit": daily_point_limit,
            "min_cash_redemption": min_cash_redemption,
        }
        for history in sorted(config.get("ruleHistory") or [], key=lambda h: h.get("timestamp") or 0):
            field = history.get("field")
            new_value = history.get("newValue")
            if field == "pointValue":
                running_settings["rupiah_per_point"] = int(new_value)
            elif field == "dailyMax":
                running_settings["daily_point_limit"] = int(new_value)
            elif field == "cashoutMin":
                running_settings["min_cash_redemption"] = int(new_value)

            changed_at = parse_datetime_ms(history.get("timestamp")) if history.get("timestamp") else date_to_completed_at(parse_date(history.get("date")))
            db.add(
                SettingsHistory(
                    family_id=family.id,
                    rupiah_per_point=running_settings["rupiah_per_point"],
                    daily_point_limit=running_settings["daily_point_limit"],
                    min_cash_redemption=running_settings["min_cash_redemption"],
                    changed_at=changed_at,
                    note=history.get("label"),
                )
            )

        await db.commit()

        family_code = family.family_code

    print("\n=== Migrasi selesai! ===")
    print(f"Nama keluarga : {family_name}")
    print(f"Kode keluarga : {family_code}  (anak pakai ini untuk login)")
    print(f"Login parent  : {admin_email}")
    if skipped:
        print(f"\nCatatan: {skipped} baris riwayat dilewati (anak/misi tidak ditemukan).")
    print("\nSemua anak perlu membuat PIN baru saat login pertama kali.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
