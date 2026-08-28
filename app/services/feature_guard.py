from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_family
from app.models.models import CompletionStatus, Family, MissionCompletion
from app.services.points import get_day_bounds

FEATURE_LABELS = {
    "quiz": "Quiz",
    "chat": "Chat",
    "agenda": "Agenda Keluarga",
    "reward": "Reward & Poin",
    "mission_evidence": "Bukti Misi",
}


def _feature_attr(feature: str) -> str:
    if feature == "reward":
        return "rewards_enabled"
    if feature == "mission_evidence":
        return "mission_evidence_enabled"
    return f"{feature}_enabled"


def require_feature(feature: str):
    async def _guard(family: Annotated[Family, Depends(get_current_family)]) -> Family:
        enabled = getattr(family, _feature_attr(feature), False)
        if not enabled:
            label = FEATURE_LABELS.get(feature, feature)
            raise HTTPException(status_code=403, detail=f"Fitur {label} belum diaktifkan untuk keluarga ini")
        return family

    return _guard


def assert_feature_enabled(family: Family, feature: str) -> None:
    enabled = getattr(family, _feature_attr(feature), False)
    if not enabled:
        label = FEATURE_LABELS.get(feature, feature)
        raise HTTPException(status_code=403, detail=f"Fitur {label} belum diaktifkan untuk keluarga ini")


def assert_rewards_enabled(family: Family) -> None:
    assert_feature_enabled(family, "reward")


async def count_approved_missions_today(
    db: AsyncSession,
    child_id: int,
    *,
    on_date: date | None = None,
) -> int:
    day = on_date or datetime.now(timezone.utc).date()
    day_start, day_end = get_day_bounds(day)
    result = await db.execute(
        select(func.count())
        .select_from(MissionCompletion)
        .where(
            MissionCompletion.child_id == child_id,
            MissionCompletion.status == CompletionStatus.APPROVED,
            MissionCompletion.completed_at >= day_start,
            MissionCompletion.completed_at < day_end,
        )
    )
    return int(result.scalar() or 0)


async def assert_daily_mission_quota(
    db: AsyncSession,
    family: Family,
    child_id: int,
    *,
    on_date: date | None = None,
) -> None:
    if family.daily_mission_limit is None:
        return
    approved_today = await count_approved_missions_today(db, child_id, on_date=on_date)
    if approved_today >= family.daily_mission_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Batas misi harian tercapai ({family.daily_mission_limit} misi/hari). Coba lagi besok atau hubungi admin.",
        )
