from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Achievement,
    BadgeDefinition,
    Child,
    ChildBadge,
    CompletionStatus,
    Family,
    MissionCompletion,
    PointTransaction,
    PunishmentRecord,
    RedemptionRequest,
    RedemptionStatus,
    RedemptionType,
    TransactionType,
    WeeklySalarySnapshot,
)
from app.services.gamification import get_level
from app.websocket.manager import ws_manager


async def get_today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def date_to_completed_at(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(
        hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )


async def get_week_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    return week_start, week_end


async def record_transaction(
    db: AsyncSession,
    child: Child,
    family: Family,
    transaction_type: TransactionType,
    points: int,
    description: str,
    reference_id: int | None = None,
    affects_lifetime: bool = True,
    created_at: datetime | None = None,
    update_streak_on_record: bool = True,
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
        description=description,
        reference_id=reference_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(tx)
    if update_streak_on_record:
        await update_streak(db, child)
    await check_badges(db, child)
    return tx


async def update_streak(db: AsyncSession, child: Child) -> None:
    today = await get_today_start()
    if child.last_activity_date:
        last = child.last_activity_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if last == today:
            return
        if last == today - timedelta(days=1):
            child.current_streak += 1
        else:
            child.current_streak = 1
    else:
        child.current_streak = 1

    child.last_activity_date = datetime.now(timezone.utc)
    child.reminder_sent_at = None
    if child.current_streak > child.longest_streak:
        child.longest_streak = child.current_streak


async def check_badges(db: AsyncSession, child: Child) -> list[ChildBadge]:
    result = await db.execute(select(BadgeDefinition))
    all_badges = result.scalars().all()

    existing = await db.execute(select(ChildBadge.badge_id).where(ChildBadge.child_id == child.id))
    existing_ids = set(existing.scalars().all())

    new_badges = []
    for badge in all_badges:
        if badge.id in existing_ids:
            continue
        earned = False
        if badge.min_lifetime_points > 0 and child.lifetime_points >= badge.min_lifetime_points:
            earned = True
        elif badge.code == "first_mission":
            count = await db.execute(
                select(func.count()).select_from(MissionCompletion).where(
                    MissionCompletion.child_id == child.id,
                    MissionCompletion.status == CompletionStatus.APPROVED,
                )
            )
            if count.scalar() >= 1:
                earned = True
        elif badge.code == "streak_7" and child.current_streak >= 7:
            earned = True
        elif badge.code == "streak_30" and child.current_streak >= 30:
            earned = True

        if earned:
            cb = ChildBadge(child_id=child.id, badge_id=badge.id)
            db.add(cb)
            new_badges.append(cb)

    return new_badges


async def get_daily_points_earned(db: AsyncSession, child_id: int, on_date: date | None = None) -> int:
    if on_date:
        day_start, day_end = get_day_bounds(on_date)
    else:
        day_start = await get_today_start()
        day_end = day_start + timedelta(days=1)
    result = await db.execute(
        select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
            PointTransaction.child_id == child_id,
            PointTransaction.created_at >= day_start,
            PointTransaction.created_at < day_end,
            PointTransaction.points > 0,
        )
    )
    return int(result.scalar() or 0)


async def get_weekly_points(db: AsyncSession, child_id: int) -> tuple[int, int, int]:
    week_start, week_end = await get_week_bounds()
    result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.child_id == child_id,
            PointTransaction.created_at >= week_start,
            PointTransaction.created_at < week_end,
        )
    )
    txs = result.scalars().all()
    earned = sum(t.points for t in txs if t.points > 0)
    deducted = abs(sum(t.points for t in txs if t.points < 0))
    return earned, deducted, earned - deducted


async def get_reward_redeemed_total(db: AsyncSession, child_id: int) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(RedemptionRequest.points), 0)).where(
            RedemptionRequest.child_id == child_id,
            RedemptionRequest.redemption_type == RedemptionType.REWARD,
            RedemptionRequest.status == RedemptionStatus.APPROVED,
        )
    )
    return int(result.scalar() or 0)


async def get_spendable_balance(db: AsyncSession, child: Child) -> tuple[int, int]:
    """Return (spendable_balance, reward_redeemed_total)."""
    reward_redeemed = await get_reward_redeemed_total(db, child.id)
    spendable = max(0, child.lifetime_points - reward_redeemed)
    spendable = min(spendable, child.active_balance)
    return spendable, reward_redeemed


async def get_points_summary(db: AsyncSession, child: Child) -> dict:
    earned, deducted, net = await get_weekly_points(db, child.id)
    spendable, reward_redeemed = await get_spendable_balance(db, child)
    cash_redeemed = await get_cash_redeemed_total(db, child.id)
    return {
        "active_balance": spendable,
        "lifetime_points": child.lifetime_points,
        "total_redeemed": child.total_redeemed,
        "reward_redeemed_total": reward_redeemed,
        "cash_redeemed_total": cash_redeemed,
        "weekly_net_points": net,
        "weekly_earned": earned,
        "weekly_deducted": deducted,
    }


async def get_cash_redeemed_total(db: AsyncSession, child_id: int) -> int:
    from app.models.models import RedemptionType

    result = await db.execute(
        select(func.coalesce(func.sum(RedemptionRequest.points), 0)).where(
            RedemptionRequest.child_id == child_id,
            RedemptionRequest.redemption_type == RedemptionType.CASH,
            RedemptionRequest.status == RedemptionStatus.APPROVED,
        )
    )
    return int(result.scalar() or 0)


async def get_redemption_breakdown(db: AsyncSession, child_id: int) -> dict:
    from app.models.models import RedemptionType

    result = await db.execute(
        select(RedemptionRequest)
        .options(selectinload(RedemptionRequest.reward))
        .where(RedemptionRequest.child_id == child_id)
        .order_by(RedemptionRequest.created_at.desc())
    )
    redemptions = []
    total_reward = 0
    total_cash = 0
    for r in result.scalars().all():
        if r.status == RedemptionStatus.APPROVED:
            if r.redemption_type == RedemptionType.REWARD:
                total_reward += r.points
            else:
                total_cash += r.points
        redemptions.append({
            "id": r.id,
            "type": r.redemption_type.value,
            "points": r.points,
            "status": r.status.value,
            "reward_title": r.reward.title if r.reward else None,
            "created_at": r.created_at.isoformat(),
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        })
    child = await db.get(Child, child_id)
    return {
        "total_redeemed": child.total_redeemed if child else 0,
        "total_reward_points": total_reward,
        "total_cash_points": total_cash,
        "redemptions": redemptions,
    }


async def get_points_for_range(
    db: AsyncSession, child_id: int, start: datetime, end: datetime
) -> tuple[int, int, int]:
    result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.child_id == child_id,
            PointTransaction.created_at >= start,
            PointTransaction.created_at < end,
        )
    )
    txs = result.scalars().all()
    earned = sum(t.points for t in txs if t.points > 0)
    deducted = abs(sum(t.points for t in txs if t.points < 0))
    return earned, deducted, earned - deducted


async def get_weekly_evaluations(db: AsyncSession, child_id: int, weeks: int = 5) -> list[dict]:
    week_start, _ = await get_week_bounds()
    evaluations = []
    for i in range(weeks):
        ws = week_start - timedelta(days=7 * i)
        we = ws + timedelta(days=7)
        earned, deducted, net = await get_points_for_range(db, child_id, ws, we)
        evaluations.append({
            "week_start": ws,
            "week_end": we,
            "points_earned": earned,
            "points_deducted": deducted,
            "net_points": net,
        })
    return evaluations


async def broadcast_family_update(family_id: int, event: str, data: dict) -> None:
    await ws_manager.broadcast(family_id, {"event": event, "data": data})


async def broadcast_child_update(family_id: int, child_id: int, event: str, data: dict) -> None:
    await ws_manager.broadcast(family_id, {"event": event, "child_id": child_id, "data": data})


async def generate_weekly_snapshots(db: AsyncSession, family: Family) -> None:
    week_start, week_end = await get_week_bounds()
    prev_start = week_start - timedelta(days=7)
    prev_end = week_start

    for child in family.children:
        if not child.is_active:
            continue
        existing = await db.execute(
            select(WeeklySalarySnapshot).where(
                WeeklySalarySnapshot.child_id == child.id,
                WeeklySalarySnapshot.week_start == prev_start,
            )
        )
        if existing.scalar_one_or_none():
            continue

        result = await db.execute(
            select(PointTransaction).where(
                PointTransaction.child_id == child.id,
                PointTransaction.created_at >= prev_start,
                PointTransaction.created_at < prev_end,
            )
        )
        txs = result.scalars().all()
        earned = sum(t.points for t in txs if t.points > 0)
        deducted = abs(sum(t.points for t in txs if t.points < 0))
        net = earned - deducted

        avg_rupiah = family.rupiah_per_point
        if txs:
            avg_rupiah = sum(t.rupiah_per_point for t in txs) // len(txs)

        snapshot = WeeklySalarySnapshot(
            child_id=child.id,
            week_start=prev_start,
            week_end=prev_end,
            points_earned=earned,
            points_deducted=deducted,
            net_points=net,
            rupiah_per_point=avg_rupiah,
            salary_rupiah=net * avg_rupiah,
        )
        db.add(snapshot)
