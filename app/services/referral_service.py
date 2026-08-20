import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tokens import generate_raw_token, hash_token, utcnow
from app.models.models import Family, Parent, ReferralInvite
from app.repositories.family_repository import FamilyRepository
from app.schemas import ReferralInviteCreate, ReferralStatsResponse
from app.services.email_service import send_referral_invite_email
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.families = FamilyRepository(db)

    async def get_stats(self, parent: Parent) -> ReferralStatsResponse:
        family = await self.families.get_by_id(parent.family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")
        if not family.referral_code:
            family.referral_code = await self.families.generate_unique_referral_code()
            await self.db.flush()

        invites = await self.db.execute(
            select(func.count()).select_from(ReferralInvite).where(
                ReferralInvite.referrer_family_id == family.id
            )
        )
        joined = await self.db.execute(
            select(func.count()).select_from(Family).where(
                Family.referred_by_family_id == family.id
            )
        )
        return ReferralStatsResponse(
            referral_code=family.referral_code,
            invites_sent=invites.scalar_one(),
            families_joined=joined.scalar_one(),
        )

    async def invite(self, parent: Parent, data: ReferralInviteCreate) -> dict:
        family = await self.families.get_by_id(parent.family_id)
        if not family or not family.referral_code:
            raise HTTPException(status_code=400, detail="Kode referral belum tersedia")

        raw = generate_raw_token()
        invite = ReferralInvite(
            referrer_family_id=family.id,
            invitee_email=data.email,
            referral_code=family.referral_code,
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(days=30),
        )
        self.db.add(invite)
        link = f"{settings.frontend_base_url}/?ref={family.referral_code}"
        sent = await send_referral_invite_email(
            to=data.email,
            referrer_name=family.family_name,
            link=link,
        )
        if not sent:
            logger.info("DEV referral invite for %s: %s", data.email, link)
        await self.db.commit()
        return {"message": f"Undangan referral dikirim ke {data.email}"}
