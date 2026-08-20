"""Controller: referral invites."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_parent
from app.core.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.models import Parent
from app.schemas import MessageResponse, ReferralInviteCreate, ReferralStatsResponse
from app.services.referral_service import ReferralService

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/stats", response_model=ReferralStatsResponse)
async def referral_stats(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ReferralService(db).get_stats(parent)


@router.post("/invite", response_model=MessageResponse)
async def referral_invite(
    data: ReferralInviteCreate,
    request: Request,
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    check_rate_limit(request, "invite", window_seconds=3600, limit=10)
    return await ReferralService(db).invite(parent, data)
