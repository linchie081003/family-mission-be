from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Family, ReferralInvite


class PlatformReferralService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def stats(self) -> dict:
        total_invites = await self.db.scalar(select(func.count()).select_from(ReferralInvite)) or 0
        total_conversions = await self.db.scalar(
            select(func.count()).select_from(Family).where(Family.referred_by_family_id.is_not(None))
        ) or 0
        families_with_code = await self.db.scalar(
            select(func.count()).select_from(Family).where(Family.referral_code.is_not(None))
        ) or 0
        conversion_rate = round((total_conversions / total_invites * 100), 1) if total_invites else 0.0
        return {
            "total_invites": total_invites,
            "total_conversions": total_conversions,
            "families_with_code": families_with_code,
            "conversion_rate": conversion_rate,
        }

    async def leaderboard(self, limit: int = 20) -> list[dict]:
        subq = (
            select(
                Family.id,
                Family.family_name,
                Family.referral_code,
                func.count(ReferralInvite.id).label("invites_sent"),
            )
            .outerjoin(ReferralInvite, ReferralInvite.referrer_family_id == Family.id)
            .group_by(Family.id)
            .subquery()
        )
        joined_subq = (
            select(
                Family.referred_by_family_id.label("referrer_id"),
                func.count(Family.id).label("families_joined"),
            )
            .where(Family.referred_by_family_id.is_not(None))
            .group_by(Family.referred_by_family_id)
            .subquery()
        )
        result = await self.db.execute(
            select(
                subq.c.id,
                subq.c.family_name,
                subq.c.referral_code,
                subq.c.invites_sent,
                func.coalesce(joined_subq.c.families_joined, 0).label("families_joined"),
            )
            .outerjoin(joined_subq, joined_subq.c.referrer_id == subq.c.id)
            .order_by(func.coalesce(joined_subq.c.families_joined, 0).desc(), subq.c.invites_sent.desc())
            .limit(min(max(limit, 1), 100))
        )
        rows = result.all()
        return [
            {
                "family_id": r.id,
                "family_name": r.family_name,
                "referral_code": r.referral_code,
                "invites_sent": r.invites_sent,
                "families_joined": r.families_joined,
            }
            for r in rows
            if r.invites_sent > 0 or r.families_joined > 0
        ]

    async def activity(self, limit: int = 50) -> list[dict]:
        result = await self.db.execute(
            select(Family)
            .where(Family.referred_by_family_id.is_not(None))
            .order_by(Family.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
        families = list(result.scalars().all())
        items = []
        for f in families:
            referrer = await self.db.get(Family, f.referred_by_family_id)
            items.append({
                "family_id": f.id,
                "family_name": f.family_name,
                "email": f.email,
                "referrer_id": referrer.id if referrer else None,
                "referrer_name": referrer.family_name if referrer else None,
                "created_at": f.created_at,
            })
        return items
