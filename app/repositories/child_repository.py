from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_pin
from app.models.models import Child


class ChildRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_by_id(self, child_id: int, family_id: int) -> Child | None:
        result = await self.db.execute(
            select(Child).where(Child.id == child_id, Child.family_id == family_id, Child.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, child_id: int, family_id: int) -> Child | None:
        result = await self.db.execute(
            select(Child).where(Child.id == child_id, Child.family_id == family_id)
        )
        return result.scalar_one_or_none()

    async def list_active_for_family(self, family_id: int) -> list[Child]:
        result = await self.db.execute(
            select(Child).where(Child.family_id == family_id, Child.is_active == True)
        )
        return list(result.scalars().all())

    async def set_pin(self, child: Child, pin: str) -> None:
        child.pin_hash = hash_pin(pin)

    async def clear_pin(self, child: Child) -> None:
        child.pin_hash = None
