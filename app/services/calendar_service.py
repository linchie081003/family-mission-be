from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import json
import time
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    CompletionStatus,
    Family,
    FamilyAgenda,
    MissionCompletion,
    PointTransaction,
    Child,
)

# #region agent log
_DEBUG_LOG = Path(__file__).resolve().parents[4] / "debug-b984bf.log"


def _agent_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    try:
        payload = {
            "sessionId": "b984bf",
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
            "timestamp": int(time.time() * 1000),
            "runId": "pre-fix",
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


# #endregion


def parse_month(month: str) -> tuple[date, date]:
    year, mon = map(int, month.split("-"))
    last_day = monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last_day)


async def build_calendar(
    db: AsyncSession,
    family_id: int,
    child_id: int,
    month: str,
    include_agenda: bool = True,
) -> dict:
    month_start, month_end = parse_month(month)
    start_dt = datetime.combine(month_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)

    completions_result = await db.execute(
        select(MissionCompletion)
        .options(selectinload(MissionCompletion.mission))
        .where(
            MissionCompletion.child_id == child_id,
            MissionCompletion.completed_at >= start_dt,
            MissionCompletion.completed_at < end_dt,
            MissionCompletion.status != CompletionStatus.REJECTED,
        )
    )
    completions = completions_result.scalars().all()

    family = await db.get(Family, family_id)
    family_flags = {
        "rewards_enabled": bool(family.rewards_enabled) if family else None,
        "daily_point_limit": family.daily_point_limit if family else None,
    }

    tx_result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.child_id == child_id,
            PointTransaction.created_at >= start_dt,
            PointTransaction.created_at < end_dt,
        )
    )
    transactions = tx_result.scalars().all()

    agenda_items = []
    if include_agenda:
        agenda_result = await db.execute(
            select(FamilyAgenda).where(
                FamilyAgenda.family_id == family_id,
                FamilyAgenda.event_date >= month_start,
                FamilyAgenda.event_date <= month_end,
                or_(FamilyAgenda.child_id == None, FamilyAgenda.child_id == child_id),
            )
        )
        agenda_items = agenda_result.scalars().all()

    days: dict[str, dict] = {}

    def ensure_day(d: date) -> dict:
        key = d.isoformat()
        if key not in days:
            days[key] = {"missions": [], "agenda": [], "net_points": 0, "point_entries": []}
        return days[key]

    for c in completions:
        d = c.completed_at.date()
        day = ensure_day(d)
        mission_points = c.mission.points if c.mission else 0
        # #region agent log
        if mission_points > 0 and c.points_awarded == 0:
            _agent_log(
                "calendar_service.py:build_calendar",
                "mission points mismatch",
                {
                    "completion_id": c.id,
                    "status": c.status.value,
                    "points_awarded": c.points_awarded,
                    "mission_points": mission_points,
                    "mission_category": c.mission.category.value if c.mission else None,
                    "child_id": child_id,
                    "completed_date": d.isoformat(),
                    **family_flags,
                },
                "A" if not family_flags.get("rewards_enabled") else "B",
            )
        _agent_log(
            "calendar_service.py:build_calendar",
            "calendar mission row",
            {
                "completion_id": c.id,
                "status": c.status.value,
                "points_awarded": c.points_awarded,
                "mission_points": mission_points,
                "child_id": child_id,
                "completed_date": d.isoformat(),
                **family_flags,
            },
            "C" if c.status.value == "pending" else "E",
        )
        # #endregion
        day["missions"].append({
            "id": c.id,
            "title": c.mission.title,
            "status": c.status.value,
            "points": c.points_awarded,
        })

    for tx in transactions:
        d = tx.created_at.date()
        day = ensure_day(d)
        day["net_points"] += tx.points
        day["point_entries"].append({
            "id": tx.id,
            "type": tx.transaction_type.value,
            "title": tx.description,
            "points": tx.points,
        })

    for item in agenda_items:
        day = ensure_day(item.event_date)
        day["agenda"].append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "time": item.event_time,
            "all_day": item.all_day,
            "color": item.color,
            "child_id": item.child_id,
        })

    
    return {"month": month, "child_id": child_id, "days": days}


async def build_family_overview(
    db: AsyncSession,
    family_id: int,
    month: str,
) -> dict:
    month_start, month_end = parse_month(month)
    children_result = await db.execute(
        select(Child).where(Child.family_id == family_id, Child.is_active == True).order_by(Child.name)
    )
    children = list(children_result.scalars().all())
    days: dict[str, dict] = {}

    def ensure_day(d: date) -> dict:
        key = d.isoformat()
        if key not in days:
            days[key] = {"family_agenda": [], "children": []}
        return days[key]

    family_agenda_result = await db.execute(
        select(FamilyAgenda).where(
            FamilyAgenda.family_id == family_id,
            FamilyAgenda.child_id.is_(None),
            FamilyAgenda.event_date >= month_start,
            FamilyAgenda.event_date <= month_end,
        )
    )
    for item in family_agenda_result.scalars().all():
        day = ensure_day(item.event_date)
        day["family_agenda"].append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "time": item.event_time,
            "all_day": item.all_day,
            "color": item.color,
            "child_id": None,
        })

    for child in children:
        cal = await build_calendar(db, family_id, child.id, month, include_agenda=True)
        child_days: dict[str, dict] = {}
        for date_key, day_data in cal["days"].items():
            personal_agenda = [a for a in day_data["agenda"] if a.get("child_id") == child.id]
            if not day_data["missions"] and not personal_agenda and day_data["net_points"] == 0:
                continue
            child_days[date_key] = {
                "child_id": child.id,
                "child_name": child.name,
                "child_color": child.color,
                "missions": day_data["missions"],
                "agenda": personal_agenda,
                "net_points": day_data["net_points"],
                "point_entries": day_data.get("point_entries", []),
            }
        for date_key, payload in child_days.items():
            day = ensure_day(date.fromisoformat(date_key))
            day["children"].append(payload)

    return {"month": month, "days": days}
