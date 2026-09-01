from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_child, get_current_family
from app.database import get_db
from app.models.models import Child, Family, Notification, RecipientRole
from app.schemas import NotificationPublic, UnreadCountResponse
from app.services.notification_features import notification_type_filter

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_public(n: Notification) -> NotificationPublic:
    return NotificationPublic(
        id=n.id,
        type=n.type.value,
        title=n.title,
        body=n.body,
        data=n.data,
        is_read=n.is_read,
        child_id=n.child_id,
        created_at=n.created_at,
    )


def _parent_filter(family_id: int):
    return and_(
        Notification.family_id == family_id,
        Notification.recipient_role == RecipientRole.PARENT,
    )


def _child_filter(family_id: int, child_id: int):
    return and_(
        Notification.family_id == family_id,
        Notification.recipient_role == RecipientRole.CHILD,
        Notification.child_id == child_id,
    )


@router.get("", response_model=list[NotificationPublic])
async def list_notifications(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: bool = False,
    limit: int = 50,
):
    q = (
        select(Notification)
        .where(_parent_filter(family.id), notification_type_filter(family))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        q = q.where(Notification.is_read == False)
    result = await db.execute(q)
    return [_to_public(n) for n in result.scalars().all()]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count_parent(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            _parent_filter(family.id),
            notification_type_filter(family),
            Notification.is_read == False,
        )
    )
    return UnreadCountResponse(count=int(result.scalar() or 0))


@router.post("/{notification_id}/read")
async def mark_read_parent(
    notification_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id, _parent_filter(family.id))
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404)
    n.is_read = True
    return {"message": "ok"}


@router.post("/read-all")
async def mark_all_read_parent(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await db.execute(
        update(Notification).where(_parent_filter(family.id), Notification.is_read == False).values(is_read=True)
    )
    return {"message": "ok"}


@router.get("/child", response_model=list[NotificationPublic])
async def list_child_notifications(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: bool = False,
    limit: int = 50,
):
    family = await db.get(Family, child.family_id)
    if not family:
        return []
    q = (
        select(Notification)
        .where(_child_filter(child.family_id, child.id), notification_type_filter(family))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        q = q.where(Notification.is_read == False)
    result = await db.execute(q)
    return [_to_public(n) for n in result.scalars().all()]


@router.get("/child/unread-count", response_model=UnreadCountResponse)
async def unread_count_child(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await db.get(Family, child.family_id)
    if not family:
        return UnreadCountResponse(count=0)
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            _child_filter(child.family_id, child.id),
            notification_type_filter(family),
            Notification.is_read == False,
        )
    )
    return UnreadCountResponse(count=int(result.scalar() or 0))


@router.post("/child/{notification_id}/read")
async def mark_read_child(
    notification_id: int,
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            _child_filter(child.family_id, child.id),
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404)
    n.is_read = True
    return {"message": "ok"}


@router.post("/child/read-all")
async def mark_all_read_child(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await db.execute(
        update(Notification).where(
            _child_filter(child.family_id, child.id),
            Notification.is_read == False,
        ).values(is_read=True)
    )
    return {"message": "ok"}
