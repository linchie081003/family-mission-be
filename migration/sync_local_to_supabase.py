"""
Salin data satu keluarga dari PostgreSQL lokal ke Supabase.

Prasyarat Supabase:
  - Project Supabase sudah dibuat
  - Backend pernah di-deploy sekali (schema + seed plan ada), ATAU jalankan dengan --init-target

Setup:
  1. Salin migration/.env.supabase.example -> migration/.env.supabase
  2. Isi TARGET_DATABASE_URL dengan URI Supabase (Session pooler, port 6543)

Jalankan:
  python migration/sync_local_to_supabase.py --family-email parent@keluarga-mission.id

Opsi:
  --init-target     Buat schema + seed plan di Supabase sebelum salin data
  --replace         Hapus keluarga dengan email sama di Supabase dulu (jika ada)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.inspection import inspect as sa_inspect

from app.core.config import settings
from app.core.database import Base
from app.models.models import (
    Achievement,
    Child,
    ChildBadge,
    Family,
    Goal,
    Mission,
    MissionCompletion,
    Parent,
    Payment,
    Plan,
    PointTransaction,
    Punishment,
    PunishmentRecord,
    RedemptionRequest,
    Reward,
    SettingsHistory,
    Subscription,
    TransactionType,
)

MIGRATION_DIR = Path(__file__).resolve().parent
SUPABASE_ENV = MIGRATION_DIR / ".env.supabase"


def engine_connect_args(url: str) -> dict:
    lower = url.lower()
    if "supabase" in lower or "ssl=require" in lower:
        return {"ssl": "require"}
    return {}


def make_session_factory(database_url: str):
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args=engine_connect_args(database_url),
    )
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def row_dict(obj, exclude: frozenset[str] = frozenset({"id"})) -> dict:
    mapper = sa_inspect(obj.__class__)
    return {
        col.key: getattr(obj, col.key)
        for col in mapper.columns
        if col.key not in exclude
    }


def load_target_url(cli_target: str | None) -> str:
    if cli_target:
        return cli_target
    env_file = dotenv_values(SUPABASE_ENV)
    target = env_file.get("TARGET_DATABASE_URL") or os.getenv("TARGET_DATABASE_URL")
    if not target:
        print("TARGET_DATABASE_URL belum diset.")
        print(f"Buat file {SUPABASE_ENV} (lihat .env.supabase.example) atau pakai --target-url")
        sys.exit(1)
    return target


async def init_target_schema(target_engine) -> None:
    from app.core.migrations import _seed_default_plans

    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _seed_default_plans(conn)
    print("Schema + seed plan di Supabase siap.")


async def delete_family_on_target(target_db: AsyncSession, email: str) -> None:
    family = await target_db.scalar(select(Family).where(Family.email == email))
    if family:
        await target_db.delete(family)
        await target_db.flush()
        print(f"  Keluarga lama di Supabase ({email}) dihapus.")


async def resolve_plan_id(target_db: AsyncSession, source_plan_id: int, source_db: AsyncSession) -> int:
    plan = await source_db.get(Plan, source_plan_id)
    if not plan:
        raise RuntimeError(f"Plan id={source_plan_id} tidak ditemukan di source")
    target_plan = await target_db.scalar(select(Plan).where(Plan.slug == plan.slug))
    if not target_plan:
        raise RuntimeError(
            f"Plan slug '{plan.slug}' tidak ada di Supabase. Jalankan dengan --init-target atau deploy backend dulu."
        )
    return target_plan.id


async def copy_upload_files(children: list[Child], upload_dir: str) -> None:
    bundle = MIGRATION_DIR / "upload_bundle"
    bundle.mkdir(exist_ok=True)
    copied = 0
    for child in children:
        if not child.avatar_url or not child.avatar_url.startswith("/uploads/"):
            continue
        src = Path(upload_dir) / child.avatar_url.removeprefix("/uploads/")
        if src.exists():
            dest = bundle / src.name
            shutil.copy2(src, dest)
            copied += 1
    if copied:
        print(f"  {copied} file avatar disalin ke {bundle}")
        print("  Upload folder ini ke volume uploads backend Render/Supabase jika perlu.")


async def sync_family(
    source_db: AsyncSession,
    target_db: AsyncSession,
    *,
    family_email: str,
) -> Family:
    source_family = await source_db.scalar(select(Family).where(Family.email == family_email))
    if not source_family:
        raise RuntimeError(f"Keluarga dengan email {family_email} tidak ditemukan di database lokal")

    family_id = source_family.id
    print(f"Menyalin keluarga: {source_family.family_name} ({source_family.email})")

    new_family = Family(**row_dict(source_family))
    target_db.add(new_family)
    await target_db.flush()

    parent_map: dict[int, int] = {}
    for parent in (
        await source_db.scalars(select(Parent).where(Parent.family_id == family_id))
    ).all():
        data = row_dict(parent)
        data["family_id"] = new_family.id
        obj = Parent(**data)
        target_db.add(obj)
        await target_db.flush()
        parent_map[parent.id] = obj.id

    child_map: dict[int, int] = {}
    source_children = list(
        (await source_db.scalars(select(Child).where(Child.family_id == family_id))).all()
    )
    for child in source_children:
        data = row_dict(child)
        data["family_id"] = new_family.id
        obj = Child(**data)
        target_db.add(obj)
        await target_db.flush()
        child_map[child.id] = obj.id

    mission_map: dict[int, int] = {}
    for mission in (
        await source_db.scalars(select(Mission).where(Mission.family_id == family_id))
    ).all():
        data = row_dict(mission)
        data["family_id"] = new_family.id
        obj = Mission(**data)
        target_db.add(obj)
        await target_db.flush()
        mission_map[mission.id] = obj.id

    punishment_map: dict[int, int] = {}
    for punishment in (
        await source_db.scalars(select(Punishment).where(Punishment.family_id == family_id))
    ).all():
        data = row_dict(punishment)
        data["family_id"] = new_family.id
        obj = Punishment(**data)
        target_db.add(obj)
        await target_db.flush()
        punishment_map[punishment.id] = obj.id

    reward_map: dict[int, int] = {}
    for reward in (
        await source_db.scalars(select(Reward).where(Reward.family_id == family_id))
    ).all():
        data = row_dict(reward)
        data["family_id"] = new_family.id
        obj = Reward(**data)
        target_db.add(obj)
        await target_db.flush()
        reward_map[reward.id] = obj.id

    for child in source_children:
        for goal in (
            await source_db.scalars(select(Goal).where(Goal.child_id == child.id))
        ).all():
            data = row_dict(goal)
            data["child_id"] = child_map[child.id]
            target_db.add(Goal(**data))

    completion_map: dict[int, int] = {}
    for child in source_children:
        for completion in (
            await source_db.scalars(select(MissionCompletion).where(MissionCompletion.child_id == child.id))
        ).all():
            data = row_dict(completion)
            data["child_id"] = child_map[child.id]
            data["mission_id"] = mission_map[completion.mission_id]
            obj = MissionCompletion(**data)
            target_db.add(obj)
            await target_db.flush()
            completion_map[completion.id] = obj.id

    punishment_record_map: dict[int, int] = {}
    for child in source_children:
        for record in (
            await source_db.scalars(select(PunishmentRecord).where(PunishmentRecord.child_id == child.id))
        ).all():
            data = row_dict(record)
            data["child_id"] = child_map[child.id]
            if record.punishment_id:
                data["punishment_id"] = punishment_map.get(record.punishment_id)
            obj = PunishmentRecord(**data)
            target_db.add(obj)
            await target_db.flush()
            punishment_record_map[record.id] = obj.id

    redemption_map: dict[int, int] = {}
    for child in source_children:
        for redemption in (
            await source_db.scalars(select(RedemptionRequest).where(RedemptionRequest.child_id == child.id))
        ).all():
            data = row_dict(redemption)
            data["child_id"] = child_map[child.id]
            if redemption.reward_id:
                data["reward_id"] = reward_map.get(redemption.reward_id)
            obj = RedemptionRequest(**data)
            target_db.add(obj)
            await target_db.flush()
            redemption_map[redemption.id] = obj.id

    for child in source_children:
        for tx in (
            await source_db.scalars(
                select(PointTransaction)
                .where(PointTransaction.child_id == child.id)
                .order_by(PointTransaction.created_at, PointTransaction.id)
            )
        ).all():
            data = row_dict(tx)
            data["child_id"] = child_map[child.id]
            ref_id = tx.reference_id
            if ref_id is not None:
                if tx.transaction_type == TransactionType.MISSION:
                    data["reference_id"] = completion_map.get(ref_id)
                elif tx.transaction_type == TransactionType.PUNISHMENT:
                    data["reference_id"] = punishment_record_map.get(ref_id)
                elif tx.transaction_type == TransactionType.REDEMPTION:
                    data["reference_id"] = redemption_map.get(ref_id)
                else:
                    data["reference_id"] = None
            target_db.add(PointTransaction(**data))

    for child in source_children:
        for badge in (
            await source_db.scalars(select(ChildBadge).where(ChildBadge.child_id == child.id))
        ).all():
            data = row_dict(badge)
            data["child_id"] = child_map[child.id]
            target_db.add(ChildBadge(**data))

        for achievement in (
            await source_db.scalars(select(Achievement).where(Achievement.child_id == child.id))
        ).all():
            data = row_dict(achievement)
            data["child_id"] = child_map[child.id]
            target_db.add(Achievement(**data))

    for history in (
        await source_db.scalars(select(SettingsHistory).where(SettingsHistory.family_id == family_id))
    ).all():
        data = row_dict(history)
        data["family_id"] = new_family.id
        target_db.add(SettingsHistory(**data))

    source_sub = await source_db.scalar(select(Subscription).where(Subscription.family_id == family_id))
    if source_sub:
        data = row_dict(source_sub)
        data["family_id"] = new_family.id
        data["plan_id"] = await resolve_plan_id(target_db, source_sub.plan_id, source_db)
        target_db.add(Subscription(**data))
        await target_db.flush()

    for payment in (
        await source_db.scalars(select(Payment).where(Payment.family_id == family_id))
    ).all():
        data = row_dict(payment)
        data["family_id"] = new_family.id
        if payment.subscription_id and source_sub:
            new_sub = await target_db.scalar(
                select(Subscription).where(Subscription.family_id == new_family.id)
            )
            data["subscription_id"] = new_sub.id if new_sub else None
        target_db.add(Payment(**data))

    await copy_upload_files(source_children, settings.upload_dir)
    return new_family


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sync keluarga dari PostgreSQL lokal ke Supabase")
    parser.add_argument("--source-url", default=settings.database_url, help="Database lokal (default: .env)")
    parser.add_argument("--target-url", help="Database Supabase (atau migration/.env.supabase)")
    parser.add_argument("--family-email", default="parent@keluarga-mission.id")
    parser.add_argument("--init-target", action="store_true", help="Buat schema + seed di Supabase")
    parser.add_argument("--replace", action="store_true", help="Hapus keluarga dengan email sama di Supabase")
    args = parser.parse_args()

    target_url = load_target_url(args.target_url)
    source_engine, source_factory = make_session_factory(args.source_url)
    target_engine, target_factory = make_session_factory(target_url)

    print("=== Sync Local -> Supabase ===")
    print(f"Source: {args.source_url.split('@')[-1]}")
    print(f"Target: {target_url.split('@')[-1]}")
    print(f"Family: {args.family_email}\n")

    if args.init_target:
        await init_target_schema(target_engine)

    async with source_factory() as source_db, target_factory() as target_db:
        if args.replace:
            await delete_family_on_target(target_db, args.family_email.lower())

        existing = await target_db.scalar(
            select(Family).where(Family.email == args.family_email.lower())
        )
        if existing and not args.replace:
            print(f"Email {args.family_email} sudah ada di Supabase. Pakai --replace untuk timpa.")
            sys.exit(1)

        new_family = await sync_family(
            source_db,
            target_db,
            family_email=args.family_email.lower(),
        )
        await target_db.commit()
        family_code = new_family.family_code
        family_name = new_family.family_name

    await source_engine.dispose()
    await target_engine.dispose()

    print("\n=== Sync selesai! ===")
    print(f"Nama keluarga : {family_name}")
    print(f"Kode keluarga : {family_code}")
    print(f"Login parent  : {args.family_email}")
    print("\nPastikan backend Render memakai DATABASE_URL Supabase yang sama.")


if __name__ == "__main__":
    asyncio.run(main())
