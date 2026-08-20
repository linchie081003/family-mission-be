from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EmailToken, EmailTokenPurpose


class EmailTokenRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        parent_id: int,
        token_hash: str,
        purpose: EmailTokenPurpose,
        expires_at: datetime,
    ) -> EmailToken:
        token = EmailToken(
            parent_id=parent_id,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def invalidate_unused(self, parent_id: int, purpose: EmailTokenPurpose) -> None:
        await self.db.execute(
            delete(EmailToken).where(
                EmailToken.parent_id == parent_id,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
        )

    async def find_valid(self, token_hash: str, purpose: EmailTokenPurpose) -> EmailToken | None:
        result = await self.db.execute(
            select(EmailToken).where(
                EmailToken.token_hash == token_hash,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            return None
        expires = token.expires_at
        if expires.tzinfo is None:
            from datetime import timezone
            expires = expires.replace(tzinfo=timezone.utc)
        from app.core.tokens import utcnow
        if expires < utcnow():
            return None
        return token

    async def mark_used(self, token: EmailToken) -> None:
        from app.core.tokens import utcnow
        token.used_at = utcnow()
