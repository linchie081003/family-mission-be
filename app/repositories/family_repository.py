from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_family_code, hash_password
from app.models.models import Family


class FamilyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, family_id: int) -> Family | None:
        return await self.db.get(Family, family_id)

    async def get_by_email(self, email: str) -> Family | None:
        result = await self.db.execute(select(Family).where(Family.email == email))
        return result.scalar_one_or_none()

    async def get_by_code(self, family_code: str) -> Family | None:
        result = await self.db.execute(select(Family).where(Family.family_code == family_code))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return (await self.get_by_email(email)) is not None

    async def generate_unique_code(self) -> str:
        code = generate_family_code()
        while await self.get_by_code(code):
            code = generate_family_code()
        return code

    async def create(self, *, email: str, password: str, family_name: str, is_active: bool = False) -> Family:
        family = Family(
            email=email,
            password_hash=hash_password(password),
            family_name=family_name,
            family_code=await self.generate_unique_code(),
            is_active=is_active,
        )
        self.db.add(family)
        await self.db.flush()
        return family
