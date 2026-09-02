from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_family
from app.core.upload_url import get_upload_url
from app.database import get_db
from app.models.models import (
    BadgeDefinition,
    Child,
    ChildBadge,
    CompletionStatus,
    Family,
    MissionCompletion,
    PointTransaction,
    RedemptionRequest,
    RedemptionStatus,
)
from app.routers.children import child_to_public
from app.schemas import (
    ChildDetailSummary,
    ChildRanking,
    ChildReportSummary,
    DashboardSummary,
    FamilyPointsSummary,
    PendingItem,
    PointsSummary,
    RedemptionSummary,
    TransactionPublic,
    WeeklyPointsReport,
)
from app.services.points import (
    get_points_summary,
    get_redemption_breakdown,
    get_spendable_balance,
    get_weekly_evaluations,
    get_weekly_points,
)
from app.services.snapshot_service import get_weekly_report_for_family
from app.services.gamification import get_level

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummary)
async def get_dashboard(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    children_result = await db.execute(
        select(Child).where(Child.family_id == family.id, Child.is_active == True)
    )
    children = children_result.scalars().all()

    ranking = []
    total_weekly = 0
    total_lifetime = 0
    total_active = 0

    for child in children:
        earned, deducted, net = await get_weekly_points(db, child.id)
        spendable, _ = await get_spendable_balance(db, child)
        total_weekly += net
        total_lifetime += child.lifetime_points
        total_active += spendable
        ranking.append(ChildRanking(
            id=child.id,
            name=child.name,
            color=child.color,
            avatar_url=get_upload_url(child.avatar_url),
            lifetime_points=child.lifetime_points,
            active_balance=spendable,
            weekly_points=net,
            level=get_level(child.lifetime_points),
            rank=0,
        ))

    ranking.sort(key=lambda x: x.weekly_points, reverse=True)
    for i, r in enumerate(ranking):
        r.rank = i + 1

    pending_missions = await db.execute(
        select(func.count()).select_from(MissionCompletion)
        .join(Child).where(Child.family_id == family.id, MissionCompletion.status == CompletionStatus.PENDING)
    )
    pending_redemptions = await db.execute(
        select(func.count()).select_from(RedemptionRequest)
        .join(Child).where(Child.family_id == family.id, RedemptionRequest.status == RedemptionStatus.PENDING)
    )
    pending_count = (pending_missions.scalar() or 0) + (pending_redemptions.scalar() or 0)

    return DashboardSummary(
        total_weekly_points=total_weekly,
        total_lifetime_points=total_lifetime,
        total_active_balance=total_active,
        pending_count=pending_count,
        children_ranking=ranking,
    )


@router.get("/pending", response_model=list[PendingItem])
async def get_pending(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    items = []

    completions = await db.execute(
        select(MissionCompletion)
        .options(selectinload(MissionCompletion.child), selectinload(MissionCompletion.mission))
        .join(Child)
        .where(Child.family_id == family.id, MissionCompletion.status == CompletionStatus.PENDING)
        .order_by(MissionCompletion.completed_at.desc())
    )
    for c in completions.scalars().all():
        items.append(PendingItem(
            id=c.id,
            type="mission",
            child_name=c.child.name,
            child_color=c.child.color,
            child_avatar_url=get_upload_url(c.child.avatar_url),
            title=c.mission.title,
            points=c.points_awarded,
            created_at=c.completed_at,
            extra={
                "mission_id": c.mission_id,
                "category": c.mission.category.value,
                "note": c.note,
                "proof_image": get_upload_url(c.proof_image),
            },
        ))

    redemptions = await db.execute(
        select(RedemptionRequest)
        .options(selectinload(RedemptionRequest.child), selectinload(RedemptionRequest.reward))
        .join(Child)
        .where(Child.family_id == family.id, RedemptionRequest.status == RedemptionStatus.PENDING)
        .order_by(RedemptionRequest.created_at.desc())
    )
    for r in redemptions.scalars().all():
        title = f"Tukar uang ({r.points} poin)" if r.redemption_type.value == "cash" else (r.reward.title if r.reward else "Tukar hadiah")
        items.append(PendingItem(
            id=r.id,
            type=r.redemption_type.value,
            child_name=r.child.name,
            child_color=r.child.color,
            child_avatar_url=get_upload_url(r.child.avatar_url),
            title=title,
            points=r.points,
            created_at=r.created_at,
        ))

    items.sort(key=lambda x: x.created_at, reverse=True)
    return items


@router.get("/child/{child_id}/detail", response_model=ChildDetailSummary)
async def get_child_detail(
    child_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Child).options(selectinload(Child.badges)).where(Child.id == child_id, Child.family_id == family.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404)

    _, _, net = await get_weekly_points(db, child.id)

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    tx_result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.child_id == child.id,
            PointTransaction.created_at >= thirty_days_ago,
        ).order_by(PointTransaction.created_at.desc()).limit(50)
    )

    badges_result = await db.execute(
        select(ChildBadge, BadgeDefinition)
        .join(BadgeDefinition)
        .where(ChildBadge.child_id == child.id)
    )
    badges = [
        {"id": bd.id, "code": bd.code, "name": bd.name, "description": bd.description, "icon": bd.icon, "earned_at": cb.earned_at}
        for cb, bd in badges_result.all()
    ]

    evaluations = await get_weekly_evaluations(db, child.id, 5)

    return ChildDetailSummary(
        child=await child_to_public(child, db),
        weekly_points=net,
        weekly_evaluations=[WeeklyPointsReport(**e) for e in evaluations],
        badges=badges,
        recent_transactions=[TransactionPublic.model_validate(t) for t in tx_result.scalars().all()],
    )


@router.get("/reports/children", response_model=list[ChildReportSummary])
async def children_reports(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    children_result = await db.execute(
        select(Child).where(Child.family_id == family.id, Child.is_active == True).order_by(Child.name)
    )
    reports = []
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    for child in children_result.scalars().all():
        _, _, net = await get_weekly_points(db, child.id)
        spendable, reward_redeemed = await get_spendable_balance(db, child)
        tx_result = await db.execute(
            select(PointTransaction).where(
                PointTransaction.child_id == child.id,
                PointTransaction.created_at >= thirty_days_ago,
            ).order_by(PointTransaction.created_at.desc()).limit(50)
        )
        evaluations = await get_weekly_evaluations(db, child.id, 5)
        reports.append(ChildReportSummary(
            id=child.id,
            name=child.name,
            color=child.color,
            avatar_url=get_upload_url(child.avatar_url),
            weekly_points=net,
            lifetime_points=child.lifetime_points,
            spendable_balance=spendable,
            reward_redeemed_total=reward_redeemed,
            recent_transactions=[TransactionPublic.model_validate(t) for t in tx_result.scalars().all()],
            weekly_evaluations=[WeeklyPointsReport(**e) for e in evaluations],
        ))
    return reports


@router.get("/points-summary", response_model=FamilyPointsSummary)
async def family_points_summary(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    children_result = await db.execute(
        select(Child).where(Child.family_id == family.id, Child.is_active == True)
    )
    children = list(children_result.scalars().all())
    summaries = []
    for c in children:
        data = await get_points_summary(db, c)
        summaries.append(PointsSummary(
            child_id=c.id,
            child_name=c.name,
            child_color=c.color,
            **data,
        ))
    return FamilyPointsSummary(
        total_lifetime_points=sum(s.lifetime_points for s in summaries),
        total_active_balance=sum(s.active_balance for s in summaries),
        total_redeemed=sum(s.total_redeemed for s in summaries),
        total_weekly_net=sum(s.weekly_net_points for s in summaries),
        children=summaries,
    )


@router.get("/child/{child_id}/points-summary", response_model=PointsSummary)
async def child_points_summary(
    child_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child = await db.get(Child, child_id)
    if not child or child.family_id != family.id:
        raise HTTPException(status_code=404)
    return PointsSummary(**await get_points_summary(db, child))


@router.get("/child/{child_id}/redemptions", response_model=RedemptionSummary)
async def child_redemptions_parent(
    child_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child = await db.get(Child, child_id)
    if not child or child.family_id != family.id:
        raise HTTPException(status_code=404)
    data = await get_redemption_breakdown(db, child_id)
    return RedemptionSummary(**data)


@router.get("/reports/weekly")
async def weekly_reports(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
    weeks: int = 5,
):
    return await get_weekly_report_for_family(db, family.id, weeks)
