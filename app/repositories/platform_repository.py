from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password, verify_password
from app.models.models import PlatformAdmin


class PlatformRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> PlatformAdmin | None:
        result = await self.db.execute(select(PlatformAdmin).where(PlatformAdmin.email == email))
        return result.scalar_one_or_none()

    async def verify_credentials(self, email: str, password: str) -> PlatformAdmin | None:
        admin = await self.get_by_email(email)
        if not admin or not verify_password(password, admin.password_hash):
            return None
        return admin

    async def seed_if_missing(self, *, email: str, password: str, name: str) -> None:
        if await self.get_by_email(email):
            return
        self.db.add(PlatformAdmin(email=email, password_hash=hash_password(password), name=name))
