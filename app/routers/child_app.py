from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.services.avatar_image import avatar_content_to_data_url

from app.core.auth import get_current_child
from app.core.config import settings
from app.core.upload_url import get_upload_url
from app.core.database import get_db
from app.core.security import validate_upload
from app.models.models import (
    BadgeDefinition,
    Child,
    ChildBadge,
    CompletionStatus,
    Family,
    Goal,
    Mission,
    MissionCategory,
    MissionCompletion,
    PointTransaction,
    RedemptionRequest,
    RedemptionStatus,
    Reward,
)
from app.routers.children import child_to_public
from app.routers.missions import mission_to_public
from app.schemas import ChildHomeData, ChildProfileUpdate, GoalCreate, GoalPublic, MissionPublic, PointsSummary, QuizSubmitRequest, ChatSendRequest, RedemptionSummary, RewardPublic, TransactionPublic, CalendarResponse, WeeklyPointsReport
from app.services.gamification import get_level_progress
from app.services.calendar_service import build_calendar
from app.services.chat_service import ChatService
from app.services.feature_guard import assert_feature_enabled, assert_rewards_enabled
from app.services.points import get_points_summary, get_redemption_breakdown, get_today_start, get_week_bounds, get_weekly_evaluations
from app.services.quiz_service import QuizService

router = APIRouter(prefix="/child-app", tags=["child-app"])


@router.get("/home", response_model=ChildHomeData)
async def child_home(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    today = await get_today_start()
    week_start, _ = await get_week_bounds()

    missions_result = await db.execute(
        select(Mission).where(
            Mission.family_id == child.family_id,
            Mission.is_active == True,
            Mission.category != MissionCategory.ADDITIONAL,
        ).order_by(Mission.sort_order)
    )
    missions = missions_result.scalars().all()

    completions_result = await db.execute(
        select(MissionCompletion).where(
            MissionCompletion.child_id == child.id,
            MissionCompletion.completed_at >= today,
        )
    )
    today_completions = {c.mission_id: c for c in completions_result.scalars().all()}

    today_missions = []
    for m in missions:
        mp = mission_to_public(m)
        if m.id in today_completions:
            c = today_completions[m.id]
            mp.completed_today = c.status != CompletionStatus.REJECTED
            mp.pending_approval = c.status == CompletionStatus.PENDING
        today_missions.append(mp)

    week_tx = await db.execute(
        select(PointTransaction).where(
            PointTransaction.child_id == child.id,
            PointTransaction.created_at >= week_start,
            PointTransaction.points > 0,
        )
    )
    weekly_earned = sum(t.points for t in week_tx.scalars().all())
    weekly_progress = min(weekly_earned / child.weekly_target, 1.0) if child.weekly_target > 0 else 0

    goal_result = await db.execute(
        select(Goal).where(Goal.child_id == child.id, Goal.is_achieved == False).order_by(Goal.created_at.desc()).limit(1)
    )
    active_goal = goal_result.scalar_one_or_none()

    badges_result = await db.execute(
        select(ChildBadge, BadgeDefinition)
        .join(BadgeDefinition)
        .where(ChildBadge.child_id == child.id)
        .order_by(ChildBadge.earned_at.desc())
        .limit(3)
    )
    recent_badges = [
        {"id": bd.id, "code": bd.code, "name": bd.name, "description": bd.description, "icon": bd.icon, "earned_at": cb.earned_at}
        for cb, bd in badges_result.all()
    ]

    family = await db.get(Family, child.family_id)

    return ChildHomeData(
        child=await child_to_public(child, db),
        today_missions=today_missions,
        weekly_progress=weekly_progress,
        active_goal=GoalPublic.model_validate(active_goal) if active_goal else None,
        recent_badges=recent_badges,
        quiz_enabled=bool(family and family.quiz_enabled),
        chat_enabled=bool(family and family.chat_enabled),
        chat_unread_count=await ChatService(db).child_unread_count(child, family) if family and family.chat_enabled else 0,
        rewards_enabled=bool(family and family.rewards_enabled),
        mission_evidence_enabled=bool(family and family.mission_evidence_enabled),
        daily_mission_limit=family.daily_mission_limit if family else None,
    )


@router.get("/missions", response_model=list[MissionPublic])
async def child_missions(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = None,
):
    today = await get_today_start()
    query = select(Mission).where(Mission.family_id == child.family_id, Mission.is_active == True)
    if category:
        query = query.where(Mission.category == category)
    result = await db.execute(query.order_by(Mission.sort_order))
    missions = result.scalars().all()

    completions = await db.execute(
        select(MissionCompletion).where(MissionCompletion.child_id == child.id, MissionCompletion.completed_at >= today)
    )
    today_map = {c.mission_id: c for c in completions.scalars().all()}

    output = []
    for m in missions:
        mp = mission_to_public(m)
        if m.id in today_map:
            c = today_map[m.id]
            mp.completed_today = c.status != CompletionStatus.REJECTED
            mp.pending_approval = c.status == CompletionStatus.PENDING
        output.append(mp)
    return output


@router.get("/history", response_model=list[TransactionPublic])
async def child_history(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 30,
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.child_id == child.id,
            PointTransaction.created_at >= since,
        ).order_by(PointTransaction.created_at.desc())
    )
    return result.scalars().all()


@router.get("/rewards", response_model=list[RewardPublic])
async def child_rewards(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    assert_rewards_enabled(family)
    result = await db.execute(
        select(Reward).where(Reward.family_id == child.family_id, Reward.is_active == True)
    )
    return result.scalars().all()


@router.get("/redemptions", response_model=RedemptionSummary)
async def child_redemptions(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    assert_rewards_enabled(family)
    data = await get_redemption_breakdown(db, child.id)
    return RedemptionSummary(**data)


@router.get("/points-summary", response_model=PointsSummary)
async def child_points_summary(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    assert_rewards_enabled(family)
    return PointsSummary(**await get_points_summary(db, child))


@router.get("/quizzes")
async def child_quizzes(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    return await QuizService(db).list_child_quizzes(child, family)


@router.get("/quizzes/{quiz_id}")
async def child_quiz_detail(
    quiz_id: int,
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    return await QuizService(db).get_quiz_for_child(child, family, quiz_id)


@router.post("/quizzes/{quiz_id}/submit")
async def child_quiz_submit(
    quiz_id: int,
    data: QuizSubmitRequest,
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    return await QuizService(db).submit_quiz(child, family, quiz_id, data.answers)


@router.get("/chat/unread-count")
async def child_chat_unread_count(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    count = await ChatService(db).child_unread_count(child, family)
    return {"count": count}


@router.get("/chat/messages")
async def child_chat_messages(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=200),
):
    family = await db.get(Family, child.family_id)
    return await ChatService(db).get_family_messages(family, limit=limit)


@router.post("/chat/messages")
async def child_chat_send(
    data: ChatSendRequest,
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    msg = await ChatService(db).send_family_message(
        family, sender_role="child", body=data.body, child=child,
    )
    return {"id": msg.id, "created_at": msg.created_at.isoformat()}


@router.post("/chat/read")
async def child_chat_read(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    count = await ChatService(db).mark_read_child(child, family)
    return {"marked_read": count}


@router.get("/goals", response_model=list[GoalPublic])
async def list_goals(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Goal).where(Goal.child_id == child.id).order_by(Goal.created_at.desc()))
    return result.scalars().all()


@router.post("/goals", response_model=GoalPublic)
async def create_goal(
    data: GoalCreate,
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    goal = Goal(child_id=child.id, title=data.title, target_points=data.target_points)
    db.add(goal)
    await db.flush()
    return goal


@router.get("/level-info")
async def level_info(child: Annotated[Child, Depends(get_current_child)]):
    current, next_lvl, progress = get_level_progress(child.lifetime_points)
    return {
        "current_level": current,
        "next_level": next_lvl,
        "progress": progress,
        "lifetime_points": child.lifetime_points,
        "active_balance": child.active_balance,
        "streak": child.current_streak,
    }


@router.patch("/profile")
async def update_child_profile(
    data: ChildProfileUpdate,
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if data.display_name is not None:
        child.display_name = data.display_name.strip() or None
    await db.commit()
    return await child_to_public(child, db)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    child: Annotated[Child, Depends(get_current_child)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    content = await file.read()
    validate_upload(file.filename or "avatar.jpg", file.content_type, len(content))
    child.avatar_url = avatar_content_to_data_url(content, file.content_type)
    await db.commit()
    return {"avatar_url": get_upload_url(child.avatar_url)}


@router.get("/calendar", response_model=CalendarResponse)
async def child_calendar(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    family = await db.get(Family, child.family_id)
    include_agenda = bool(family and family.agenda_enabled)
    data = await build_calendar(db, child.family_id, child.id, month, include_agenda=include_agenda)
    return CalendarResponse(**data)


@router.get("/weekly-evaluations", response_model=list[WeeklyPointsReport])
async def child_weekly_evaluations(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    evaluations = await get_weekly_evaluations(db, child.id, 5)
    return [WeeklyPointsReport(**e) for e in evaluations]
