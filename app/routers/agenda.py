from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_child, get_current_family
from app.database import get_db
from app.models.models import Child, Family, FamilyAgenda, NotificationType
from app.schemas import AgendaCreate, AgendaPublic, AgendaUpdate, CalendarResponse, FamilyOverviewCalendarResponse
from app.services.calendar_service import build_calendar, build_family_overview, parse_month
from app.services.audit_service import log_audit
from app.services.feature_guard import assert_feature_enabled, require_feature
from app.services.notification_service import notify_child, notify_parent

router = APIRouter(prefix="/agenda", tags=["agenda"])


def _to_public(item: FamilyAgenda) -> AgendaPublic:
    return AgendaPublic(
        id=item.id,
        title=item.title,
        description=item.description,
        event_date=item.event_date.isoformat(),
        event_time=item.event_time,
        all_day=item.all_day,
        color=item.color,
        child_id=item.child_id,
        reminder_hours_before=item.reminder_hours_before,
        created_at=item.created_at,
    )


async def _get_child_in_family(db: AsyncSession, child_id: int, family_id: int) -> Child:
    result = await db.execute(select(Child).where(Child.id == child_id, Child.family_id == family_id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
    return child


@router.get("", response_model=list[AgendaPublic])
async def list_agenda(
    family: Annotated[Family, Depends(require_feature("agenda"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
):
    q = select(FamilyAgenda).where(FamilyAgenda.family_id == family.id).order_by(FamilyAgenda.event_date)
    if month:
        start, end = parse_month(month)
        q = q.where(FamilyAgenda.event_date >= start, FamilyAgenda.event_date <= end)
    result = await db.execute(q)
    return [_to_public(i) for i in result.scalars().all()]


@router.post("", response_model=AgendaPublic)
async def create_agenda(
    data: AgendaCreate,
    family: Annotated[Family, Depends(require_feature("agenda"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if data.child_id:
        await _get_child_in_family(db, data.child_id, family.id)

    item = FamilyAgenda(
        family_id=family.id,
        title=data.title,
        description=data.description,
        event_date=date.fromisoformat(data.event_date),
        event_time=data.event_time,
        all_day=data.all_day,
        color=data.color,
        child_id=data.child_id,
        reminder_hours_before=data.reminder_hours_before,
    )
    db.add(item)
    await db.flush()

    if data.child_id:
        child = await db.get(Child, data.child_id)
        await notify_child(
            db, family.id, data.child_id, NotificationType.AGENDA,
            "Agenda baru",
            f"{data.title} — {data.event_date}",
            data={"agenda_id": item.id},
        )
    else:
        children = await db.execute(select(Child).where(Child.family_id == family.id, Child.is_active == True))
        for child in children.scalars().all():
            await notify_child(
                db, family.id, child.id, NotificationType.AGENDA,
                "Agenda keluarga",
                f"{data.title} — {data.event_date}",
                data={"agenda_id": item.id},
            )

    await log_audit(
        db, family.id, "parent", family.family_name, "create", "agenda",
        f"Menambah agenda: {data.title} ({data.event_date})",
        entity_id=item.id,
        details={"title": data.title, "event_date": data.event_date, "child_id": data.child_id},
    )

    return _to_public(item)


@router.patch("/{agenda_id}", response_model=AgendaPublic)
async def update_agenda(
    agenda_id: int,
    data: AgendaUpdate,
    family: Annotated[Family, Depends(require_feature("agenda"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(FamilyAgenda).where(FamilyAgenda.id == agenda_id, FamilyAgenda.family_id == family.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404)

    if data.title is not None:
        item.title = data.title
    if data.description is not None:
        item.description = data.description
    if data.event_date is not None:
        item.event_date = date.fromisoformat(data.event_date)
    if data.event_time is not None:
        item.event_time = data.event_time
    if data.all_day is not None:
        item.all_day = data.all_day
    if data.color is not None:
        item.color = data.color
    if data.child_id is not None:
        if data.child_id:
            await _get_child_in_family(db, data.child_id, family.id)
        item.child_id = data.child_id
    if data.reminder_hours_before is not None:
        item.reminder_hours_before = data.reminder_hours_before
        item.reminder_sent_at = None

    return _to_public(item)


@router.delete("/{agenda_id}")
async def delete_agenda(
    agenda_id: int,
    family: Annotated[Family, Depends(require_feature("agenda"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(FamilyAgenda).where(FamilyAgenda.id == agenda_id, FamilyAgenda.family_id == family.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404)
    title = item.title
    await db.delete(item)
    await log_audit(
        db, family.id, "parent", family.family_name, "delete", "agenda",
        f"Menghapus agenda: {title}",
        entity_id=agenda_id,
    )
    return {"message": "Agenda dihapus"}


@router.get("/calendar-overview", response_model=FamilyOverviewCalendarResponse)
async def family_calendar_overview(
    family: Annotated[Family, Depends(require_feature("agenda"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    data = await build_family_overview(db, family.id, month)
    return FamilyOverviewCalendarResponse(**data)


@router.get("/calendar/{child_id}", response_model=CalendarResponse)
async def parent_calendar(
    child_id: int,
    family: Annotated[Family, Depends(require_feature("agenda"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    await _get_child_in_family(db, child_id, family.id)
    data = await build_calendar(db, family.id, child_id, month, include_agenda=True)
    return CalendarResponse(**data)


@router.get("/child/list", response_model=list[AgendaPublic])
async def child_list_agenda(
    child: Annotated[Child, Depends(get_current_child)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
):
    family = await db.get(Family, child.family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")
    assert_feature_enabled(family, "agenda")
    q = select(FamilyAgenda).where(
        FamilyAgenda.family_id == child.family_id,
        or_(FamilyAgenda.child_id == None, FamilyAgenda.child_id == child.id),
    ).order_by(FamilyAgenda.event_date)
    if month:
        start, end = parse_month(month)
        q = q.where(FamilyAgenda.event_date >= start, FamilyAgenda.event_date <= end)
    result = await db.execute(q)
    return [_to_public(i) for i in result.scalars().all()]
