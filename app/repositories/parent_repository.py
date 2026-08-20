from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.models.models import Parent, ParentRole


class ParentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, parent_id: int) -> Parent | None:
        return await self.db.get(Parent, parent_id)

    async def get_by_email(self, email: str) -> Parent | None:
        result = await self.db.execute(select(Parent).where(Parent.email == email))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return (await self.get_by_email(email)) is not None

    async def list_by_family(self, family_id: int) -> list[Parent]:
        result = await self.db.execute(
            select(Parent).where(Parent.family_id == family_id, Parent.is_active == True).order_by(Parent.id)
        )
        return list(result.scalars().all())

    async def count_by_role(self, family_id: int, role: ParentRole) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Parent).where(
                Parent.family_id == family_id,
                Parent.role == role,
                Parent.is_active == True,
            )
        )
        return result.scalar_one()

    async def create(
        self,
        *,
        family_id: int,
        email: str,
        password: str,
        name: str,
        role: ParentRole,
        is_primary: bool = False,
        email_verified: bool = False,
        terms_accepted_at=None,
        privacy_accepted_at=None,
        parental_consent_at=None,
        child_data_protection_accepted_at=None,
        legal_doc_version: str | None = None,
    ) -> Parent:
        parent = Parent(
            family_id=family_id,
            email=email,
            password_hash=hash_password(password),
            name=name,
            role=role,
            is_primary=is_primary,
            email_verified=email_verified,
            terms_accepted_at=terms_accepted_at,
            privacy_accepted_at=privacy_accepted_at,
            parental_consent_at=parental_consent_at,
            child_data_protection_accepted_at=child_data_protection_accepted_at,
            legal_doc_version=legal_doc_version,
        )
        self.db.add(parent)
        await self.db.flush()
        return parent
