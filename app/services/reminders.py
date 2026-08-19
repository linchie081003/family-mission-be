from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.models import Child, FamilyAgenda, MissionCompletion, NotificationType
from app.services.notification_service import notify_child, notify_parent


async def _last_mission_activity(db: AsyncSession, child_id: int) -> datetime | None:
    result = await db.execute(
        select(func.max(MissionCompletion.completed_at)).where(MissionCompletion.child_id == child_id)
    )
    return result.scalar()


async def check_inactivity_reminders():
    """Send reminder if child has no mission update in 1 day."""
    async with async_session() as db:
        one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        result = await db.execute(select(Child).where(Child.is_active == True))
        children = result.scalars().all()

        for child in children:
            if child.reminder_sent_at and child.reminder_sent_at > one_day_ago:
                continue

            last_mission = await _last_mission_activity(db, child.id)
            last_update = child.last_activity_date
            if last_mission and (not last_update or last_mission > last_update):
                last_update = last_mission

            if last_update and last_update >= one_day_ago:
                continue

            message = f"Hai {child.name}! Sudah 1 hari belum isi misi. Yuk kerjakan task hari ini! 📝"

            await notify_child(
                db, child.family_id, child.id, NotificationType.INACTIVITY,
                "Pengingat isi misi",
                message,
                data={"child_name": child.name},
            )

            child.reminder_sent_at = datetime.now(timezone.utc)

        await db.commit()


async def check_agenda_reminders():
    """Notify about upcoming agenda events."""
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(FamilyAgenda).where(
                FamilyAgenda.reminder_hours_before != None,
                FamilyAgenda.reminder_sent_at == None,
            )
        )
        items = result.scalars().all()

        for item in items:
            event_dt = datetime.combine(item.event_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            if item.event_time and not item.all_day:
                h, m = map(int, item.event_time.split(":"))
                event_dt = event_dt.replace(hour=h, minute=m)

            remind_at = event_dt - timedelta(hours=item.reminder_hours_before)
            if now < remind_at:
                continue

            title = f"Agenda: {item.title}"
            body = f"{item.title} — {item.event_date.isoformat()}"
            if item.event_time:
                body += f" pukul {item.event_time}"

            if item.child_id:
                await notify_child(
                    db, item.family_id, item.child_id, NotificationType.AGENDA,
                    title, body, data={"agenda_id": item.id},
                )
            else:
                children = await db.execute(
                    select(Child).where(Child.family_id == item.family_id, Child.is_active == True)
                )
                for child in children.scalars().all():
                    await notify_child(
                        db, item.family_id, child.id, NotificationType.AGENDA,
                        title, body, data={"agenda_id": item.id},
                    )

            await notify_parent(
                db, item.family_id, NotificationType.AGENDA,
                title, body, data={"agenda_id": item.id},
            )

            item.reminder_sent_at = now

        await db.commit()
