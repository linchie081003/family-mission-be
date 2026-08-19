from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PARENT_AUDIT_ENTITY_TYPES
from app.models.models import AuditLog, SettingsHistory


class SettingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_history(
        self,
        *,
        family_id: int,
        rupiah_per_point: int,
        daily_point_limit: int,
        min_cash_redemption: int,
        note: str | None,
    ) -> SettingsHistory:
        entry = SettingsHistory(
            family_id=family_id,
            rupiah_per_point=rupiah_per_point,
            daily_point_limit=daily_point_limit,
            min_cash_redemption=min_cash_redemption,
            note=note,
        )
        self.db.add(entry)
        return entry

    async def list_history(self, family_id: int) -> list[SettingsHistory]:
        result = await self.db.execute(
            select(SettingsHistory)
            .where(SettingsHistory.family_id == family_id)
            .order_by(SettingsHistory.changed_at.desc())
        )
        return list(result.scalars().all())


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_parent_visible(self, family_id: int, limit: int = 100) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.family_id == family_id, AuditLog.entity_type.in_(PARENT_AUDIT_ENTITY_TYPES))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
