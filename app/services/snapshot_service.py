from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Child, Family, Quiz, QuizAttempt, WeeklySalarySnapshot


async def run_all_weekly_snapshots(db: AsyncSession) -> int:
    from app.services.points import generate_weekly_snapshots

    result = await db.execute(
        select(Family).options(selectinload(Family.children)).where(Family.is_active == True)
    )
    count = 0
    for family in result.scalars().all():
        await generate_weekly_snapshots(db, family)
        count += 1
    return count


async def get_weekly_report_for_family(db: AsyncSession, family_id: int, weeks: int = 5) -> list[dict]:
    children_result = await db.execute(
        select(Child).where(Child.family_id == family_id, Child.is_active == True)
    )
    children = list(children_result.scalars().all())
    reports = []

    for child in children:
        snapshots = await db.execute(
            select(WeeklySalarySnapshot)
            .where(WeeklySalarySnapshot.child_id == child.id)
            .order_by(WeeklySalarySnapshot.week_start.desc())
            .limit(weeks)
        )
        child_weeks = []
        for snap in snapshots.scalars().all():
            child_weeks.append({
                "week_start": snap.week_start.isoformat(),
                "week_end": snap.week_end.isoformat(),
                "points_earned": snap.points_earned,
                "points_deducted": snap.points_deducted,
                "net_points": snap.net_points,
                "rupiah_per_point": snap.rupiah_per_point,
                "salary_rupiah": snap.salary_rupiah,
            })
        reports.append({
            "child_id": child.id,
            "child_name": child.name,
            "child_color": child.color,
            "weeks": child_weeks,
        })
    return reports
