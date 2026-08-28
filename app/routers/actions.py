from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_child, get_current_family
from app.database import get_db
from app.models.models import (
    Achievement,
    Child,
    CompletionStatus,
    Family,
    Mission,
    MissionCategory,
    MissionCompletion,
    NotificationType,
    PunishmentRecord,
    RedemptionRequest,
    RedemptionStatus,
    RedemptionType,
    Reward,
    TransactionType,
)
from app.schemas import (
    AchievementCreate,
    MissionCompleteRequest,
    ParentMissionRecordRequest,
    PunishmentRecordCreate,
    RedemptionCreate,
)
from app.services.points import (
    broadcast_child_update,
    broadcast_family_update,
    check_badges,
    date_to_completed_at,
    get_daily_points_earned,
    get_day_bounds,
    get_spendable_balance,
    get_today_start,
    record_transaction,
    update_streak,
)
from app.services.notification_service import notify_child, notify_parent
from app.services.audit_service import log_audit
from app.services.feature_guard import assert_daily_mission_quota, assert_rewards_enabled
from app.services.proof_image import validate_proof_image

router = APIRouter(prefix="/actions", tags=["actions"])


async def get_child_in_family(db: AsyncSession, child_id: int, family_id: int) -> Child:
    result = await db.execute(select(Child).where(Child.id == child_id, Child.family_id == family_id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
    return child


async def _approve_mission_completion(
    db: AsyncSession,
    family: Family,
    child: Child,
    mission: Mission,
    completion: MissionCompletion,
    *,
    completed_at: datetime | None = None,
) -> int:
    completed_at = completed_at or completion.completed_at or datetime.now(timezone.utc)
    is_today = completed_at.date() == datetime.now(timezone.utc).date()

    await assert_daily_mission_quota(db, family, child.id, on_date=completed_at.date())

    completion.status = CompletionStatus.APPROVED
    completion.reviewed_at = datetime.now(timezone.utc)
    completion.completed_at = completed_at

    if not family.rewards_enabled:
        completion.points_awarded = 0
        if is_today:
            child.last_activity_date = datetime.now(timezone.utc)
            child.reminder_sent_at = None
        return 0

    points = mission.points
    if points > 0:
        daily = await get_daily_points_earned(db, child.id, on_date=completed_at.date())
        if daily + points > family.daily_point_limit:
            points = max(0, family.daily_point_limit - daily)

    completion.points_awarded = points

    if points > 0:
        await record_transaction(
            db, child, family, TransactionType.MISSION, points,
            f"Misi: {mission.title}", completion.id,
            created_at=completed_at,
            update_streak_on_record=is_today,
        )
    else:
        await record_transaction(
            db, child, family, TransactionType.MISSION, 0,
            f"Ibadah: {mission.title}", completion.id,
            affects_lifetime=False,
            created_at=completed_at,
            update_streak_on_record=False,
        )
        if is_today:
            await update_streak(db, child)

    await check_badges(db, child)
    return points


@router.post("/child/{child_id}/complete-mission")
async def child_complete_mission(
    child_id: int,
    data: MissionCompleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    child_auth: Annotated[Child, Depends(get_current_child)],
):
    if child_auth.id != child_id:
        raise HTTPException(status_code=403, detail="Akses ditolak")

    mission_result = await db.execute(
        select(Mission).where(Mission.id == data.mission_id, Mission.family_id == child_auth.family_id, Mission.is_active == True)
    )
    mission = mission_result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Misi tidak ditemukan")

    if mission.category == MissionCategory.ADDITIONAL:
        raise HTTPException(status_code=400, detail="Misi tambahan hanya bisa dicatat orang tua")

    today = await get_today_start()
    existing = await db.execute(
        select(MissionCompletion).where(
            MissionCompletion.child_id == child_id,
            MissionCompletion.mission_id == data.mission_id,
            MissionCompletion.completed_at >= today,
            MissionCompletion.status != CompletionStatus.REJECTED,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Misi sudah dicatat hari ini")

    family = await db.get(Family, child_auth.family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

    proof_image = validate_proof_image(
        data.proof_image,
        required=family.mission_evidence_enabled,
    )

    completion = MissionCompletion(
        child_id=child_id,
        mission_id=data.mission_id,
        status=CompletionStatus.PENDING,
        points_awarded=mission.points if family.rewards_enabled else 0,
        note=data.note,
        proof_image=proof_image,
    )
    db.add(completion)
    await db.flush()

    child_auth.last_activity_date = datetime.now(timezone.utc)
    child_auth.reminder_sent_at = None

    await broadcast_family_update(child_auth.family_id, "mission_pending", {
        "completion_id": completion.id,
        "child_name": child_auth.name,
        "mission_title": mission.title,
    })
    await notify_parent(
        db, child_auth.family_id, NotificationType.MISSION_PENDING,
        "Misi menunggu persetujuan",
        f"{child_auth.name}: {mission.title}",
        child_id=child_id,
        data={"completion_id": completion.id, "mission_title": mission.title},
    )
    await log_audit(
        db, child_auth.family_id, "child", child_auth.name, "submit", "mission",
        f"{child_auth.name} mengisi misi: {mission.title}",
        entity_id=completion.id,
        details={"mission_id": mission.id, "mission_title": mission.title},
    )

    return {"message": "Misi dicatat, menunggu persetujuan orang tua", "completion_id": completion.id}


@router.post("/child/{child_id}/record-mission")
async def parent_record_mission(
    child_id: int,
    data: ParentMissionRecordRequest,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Orang tua catat misi anak langsung (tanpa approval), bisa backdate."""
    child = await get_child_in_family(db, child_id, family.id)

    mission_result = await db.execute(
        select(Mission).where(
            Mission.id == data.mission_id,
            Mission.family_id == family.id,
            Mission.is_active == True,
        )
    )
    mission = mission_result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Misi tidak ditemukan")

    today = datetime.now(timezone.utc).date()
    completed_date = date.fromisoformat(data.completed_date) if data.completed_date else today
    if completed_date > today:
        raise HTTPException(status_code=400, detail="Tanggal tidak boleh di masa depan")

    day_start, day_end = get_day_bounds(completed_date)
    existing = await db.execute(
        select(MissionCompletion).where(
            MissionCompletion.child_id == child_id,
            MissionCompletion.mission_id == data.mission_id,
            MissionCompletion.completed_at >= day_start,
            MissionCompletion.completed_at < day_end,
            MissionCompletion.status != CompletionStatus.REJECTED,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Misi sudah dicatat pada tanggal tersebut")

    completed_at = date_to_completed_at(completed_date)
    proof_image = validate_proof_image(data.proof_image, required=False)
    completion = MissionCompletion(
        child_id=child_id,
        mission_id=data.mission_id,
        status=CompletionStatus.PENDING,
        points_awarded=mission.points if family.rewards_enabled else 0,
        note=data.note,
        proof_image=proof_image,
        completed_at=completed_at,
    )
    db.add(completion)
    await db.flush()

    points = await _approve_mission_completion(
        db, family, child, mission, completion, completed_at=completed_at,
    )

    if completed_date == today:
        child.last_activity_date = datetime.now(timezone.utc)
        child.reminder_sent_at = None

    await broadcast_child_update(family.id, child.id, "mission_approved", {
        "points": points,
        "mission_title": mission.title,
        "new_balance": child.active_balance,
        "new_level": __import__("app.services.gamification", fromlist=["get_level"]).get_level(child.lifetime_points),
        "recorded_by_parent": True,
    })
    await notify_child(
        db, family.id, child.id, NotificationType.MISSION_APPROVED,
        "Misi dicatat orang tua ✅",
        f"{mission.title}" + (f" (+{points} poin)" if points > 0 else "") + f" · {completed_date.isoformat()}",
        data={"completion_id": completion.id, "points": points, "completed_date": completed_date.isoformat()},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "create", "mission",
        f"Mencatat misi {child.name}: {mission.title} ({completed_date.isoformat()})",
        entity_id=completion.id,
        details={
            "child_id": child.id,
            "mission_id": mission.id,
            "completed_date": completed_date.isoformat(),
            "points": points,
        },
    )

    return {
        "message": "Misi berhasil dicatat",
        "completion_id": completion.id,
        "points_awarded": points,
        "completed_date": completed_date.isoformat(),
    }


@router.post("/completions/{completion_id}/approve")
async def approve_completion(
    completion_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(MissionCompletion)
        .options(selectinload(MissionCompletion.mission), selectinload(MissionCompletion.child))
        .where(MissionCompletion.id == completion_id)
    )
    completion = result.scalar_one_or_none()
    if not completion or completion.child.family_id != family.id:
        raise HTTPException(status_code=404, detail="Completion tidak ditemukan")
    if completion.status != CompletionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Sudah diproses")

    child = completion.child
    mission = completion.mission
    points = await _approve_mission_completion(db, family, child, mission, completion)

    new_badges = await check_badges(db, child)

    await broadcast_child_update(family.id, child.id, "mission_approved", {
        "points": points,
        "mission_title": mission.title,
        "new_balance": child.active_balance,
        "new_level": __import__("app.services.gamification", fromlist=["get_level"]).get_level(child.lifetime_points),
        "new_badges": [b.badge_id for b in new_badges],
    })
    await notify_child(
        db, family.id, child.id, NotificationType.MISSION_APPROVED,
        "Misi disetujui! 🎉",
        f"{mission.title}" + (f" (+{points} poin)" if points > 0 else ""),
        data={"completion_id": completion.id, "points": points},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "approve", "mission",
        f"Menyetujui misi {child.name}: {mission.title} (+{points} poin)",
        entity_id=completion.id,
        details={"child_id": child.id, "points": points},
    )

    return {"message": "Misi disetujui", "points_awarded": points}


@router.post("/completions/{completion_id}/reject")
async def reject_completion(
    completion_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(MissionCompletion).options(selectinload(MissionCompletion.child)).where(MissionCompletion.id == completion_id)
    )
    completion = result.scalar_one_or_none()
    if not completion or completion.child.family_id != family.id:
        raise HTTPException(status_code=404)
    completion.status = CompletionStatus.REJECTED
    completion.reviewed_at = datetime.now(timezone.utc)

    await broadcast_child_update(family.id, completion.child_id, "mission_rejected", {"completion_id": completion_id})
    await notify_child(
        db, family.id, completion.child_id, NotificationType.MISSION_REJECTED,
        "Misi ditolak",
        "Misi hari ini perlu dicoba lagi atau hubungi orang tua.",
        data={"completion_id": completion_id},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "reject", "mission",
        f"Menolak misi anak (completion #{completion_id})",
        entity_id=completion_id,
    )
    return {"message": "Misi ditolak"}


@router.post("/child/{child_id}/achievement")
async def record_achievement(
    child_id: int,
    data: AchievementCreate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    assert_rewards_enabled(family)
    child = await get_child_in_family(db, child_id, family.id)
    achievement = Achievement(child_id=child.id, title=data.title, points=data.points, note=data.note)
    db.add(achievement)
    await db.flush()

    await record_transaction(
        db, child, family, TransactionType.ACHIEVEMENT, data.points,
        f"🌟 Pencapaian: {data.title}", achievement.id,
    )

    await broadcast_child_update(family.id, child.id, "achievement", {
        "title": data.title,
        "points": data.points,
        "new_balance": child.active_balance,
    })
    await notify_child(
        db, family.id, child.id, NotificationType.ACHIEVEMENT,
        "Pencapaian baru! 🌟",
        f"{data.title} (+{data.points} poin)",
        data={"achievement_id": achievement.id, "points": data.points},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "create", "achievement",
        f"Pencapaian {child.name}: {data.title} (+{data.points} poin)",
        entity_id=achievement.id,
    )

    return {"message": "Pencapaian dicatat", "points": data.points}


@router.post("/child/{child_id}/punishment")
async def record_punishment(
    child_id: int,
    data: PunishmentRecordCreate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    assert_rewards_enabled(family)
    child = await get_child_in_family(db, child_id, family.id)
    record = PunishmentRecord(
        child_id=child.id,
        punishment_id=data.punishment_id,
        title=data.title,
        points_deducted=data.points_deducted,
        note=data.note,
    )
    db.add(record)
    await db.flush()

    deduct = -abs(data.points_deducted)
    await record_transaction(
        db, child, family, TransactionType.PUNISHMENT, deduct,
        f"⚠️ Punishment: {data.title}", record.id, affects_lifetime=False,
    )

    await broadcast_child_update(family.id, child.id, "punishment", {
        "title": data.title,
        "points": deduct,
        "new_balance": child.active_balance,
    })
    await notify_child(
        db, family.id, child.id, NotificationType.PUNISHMENT,
        "Poin dikurangi",
        f"{data.title} ({deduct} poin)",
        data={"record_id": record.id, "points": deduct},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "create", "punishment",
        f"Punishment {child.name}: {data.title} ({deduct} poin)",
        entity_id=record.id,
    )

    return {"message": "Punishment dicatat", "points_deducted": data.points_deducted}


async def _create_redemption(db: AsyncSession, child: Child, fam: Family, data: RedemptionCreate):
    assert_rewards_enabled(fam)
    spendable, _ = await get_spendable_balance(db, child)
    balance_limit = spendable if data.redemption_type == "reward" else child.active_balance

    if data.points <= 0 or data.points > balance_limit:
        raise HTTPException(status_code=400, detail="Poin tidak valid")

    if data.redemption_type == "cash" and data.points < fam.min_cash_redemption:
        raise HTTPException(status_code=400, detail=f"Minimal tukar uang: {fam.min_cash_redemption} poin")

    if data.redemption_type == "reward":
        if not data.reward_id:
            raise HTTPException(status_code=400, detail="Reward ID diperlukan")
        reward_result = await db.execute(
            select(Reward).where(
                Reward.id == data.reward_id,
                Reward.family_id == fam.id,
                Reward.is_active == True,
            )
        )
        reward = reward_result.scalar_one_or_none()
        if not reward:
            raise HTTPException(status_code=404, detail="Reward tidak ditemukan")
        if data.points != reward.points_cost:
            raise HTTPException(status_code=400, detail=f"Hadiah membutuhkan tepat {reward.points_cost} poin")

    redemption = RedemptionRequest(
        child_id=child.id,
        redemption_type=RedemptionType(data.redemption_type),
        reward_id=data.reward_id,
        points=data.points,
        rupiah_per_point=fam.rupiah_per_point,
        note=data.note,
    )
    db.add(redemption)
    await db.flush()

    await broadcast_family_update(fam.id, "redemption_pending", {
        "redemption_id": redemption.id,
        "child_name": child.name,
        "type": data.redemption_type,
        "points": data.points,
    })
    await notify_parent(
        db, fam.id, NotificationType.REDEMPTION_PENDING,
        "Permintaan penukaran",
        f"{child.name}: {data.points} poin ({data.redemption_type})",
        child_id=child.id,
        data={"redemption_id": redemption.id, "points": data.points},
    )
    await log_audit(
        db, fam.id, "child", child.name, "request", "redemption",
        f"{child.name} mengajukan penukaran {data.points} poin ({data.redemption_type})",
        entity_id=redemption.id,
    )
    return {"message": "Permintaan penukaran diajukan", "redemption_id": redemption.id}


@router.post("/child/redeem")
async def child_request_redemption(
    data: RedemptionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    child: Annotated[Child, Depends(get_current_child)],
):
    fam = await db.get(Family, child.family_id)
    return await _create_redemption(db, child, fam, data)


@router.post("/redemptions/{redemption_id}/approve")
async def approve_redemption(
    redemption_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    assert_rewards_enabled(family)
    result = await db.execute(
        select(RedemptionRequest).options(selectinload(RedemptionRequest.child)).where(RedemptionRequest.id == redemption_id)
    )
    redemption = result.scalar_one_or_none()
    if not redemption or redemption.child.family_id != family.id:
        raise HTTPException(status_code=404)
    if redemption.status != RedemptionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Sudah diproses")

    child = redemption.child
    if child.active_balance < redemption.points:
        raise HTTPException(status_code=400, detail="Saldo anak tidak cukup")

    redemption.status = RedemptionStatus.APPROVED
    redemption.reviewed_at = datetime.now(timezone.utc)

    await record_transaction(
        db, child, family, TransactionType.REDEMPTION, -redemption.points,
        f"Penukaran {'uang tunai' if redemption.redemption_type == RedemptionType.CASH else 'hadiah'}",
        redemption.id, affects_lifetime=False,
    )
    child.total_redeemed += redemption.points

    await broadcast_child_update(family.id, child.id, "redemption_approved", {
        "points": redemption.points,
        "type": redemption.redemption_type.value,
        "new_balance": child.active_balance,
    })
    await notify_child(
        db, family.id, child.id, NotificationType.REDEMPTION_APPROVED,
        "Penukaran disetujui! 🎁",
        f"{redemption.points} poin berhasil ditukar",
        data={"redemption_id": redemption.id},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "approve", "redemption",
        f"Menyetujui penukaran {child.name}: {redemption.points} poin",
        entity_id=redemption.id,
    )

    return {"message": "Penukaran disetujui"}


@router.post("/redemptions/{redemption_id}/reject")
async def reject_redemption(
    redemption_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(RedemptionRequest).options(selectinload(RedemptionRequest.child)).where(RedemptionRequest.id == redemption_id)
    )
    redemption = result.scalar_one_or_none()
    if not redemption or redemption.child.family_id != family.id:
        raise HTTPException(status_code=404)
    redemption.status = RedemptionStatus.REJECTED
    redemption.reviewed_at = datetime.now(timezone.utc)

    await broadcast_child_update(family.id, redemption.child_id, "redemption_rejected", {"redemption_id": redemption_id})
    await notify_child(
        db, family.id, redemption.child_id, NotificationType.REDEMPTION_REJECTED,
        "Penukaran ditolak",
        "Permintaan penukaran tidak disetujui orang tua.",
        data={"redemption_id": redemption_id},
    )
    await log_audit(
        db, family.id, "parent", family.family_name, "reject", "redemption",
        f"Menolak penukaran (id #{redemption_id})",
        entity_id=redemption_id,
    )
    return {"message": "Penukaran ditolak"}
