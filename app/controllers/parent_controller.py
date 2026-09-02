"""Controller: co-parent management."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_parent
from app.core.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.models import Parent
from app.schemas import AcceptParentInviteRequest, MessageResponse, ParentInviteCreate, ParentInviteResponse, ParentPublic
from app.services.parent_service import ParentService

router = APIRouter(prefix="/parents", tags=["parents"])


@router.get("", response_model=list[ParentPublic])
async def list_parents(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ParentService(db).list_parents(parent)


@router.post("/invite", response_model=ParentInviteResponse)
async def invite_parent(
    data: ParentInviteCreate,
    request: Request,
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "invite", window_seconds=3600, limit=10)
    return await ParentService(db).invite(parent, data)


@router.post("/accept-invite", response_model=MessageResponse)
async def accept_invite(
    data: AcceptParentInviteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ParentService(db).accept_invite(data)


@router.get("/invites/pending")
async def list_pending_invites(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ParentService(db).list_pending_invites(parent)


@router.post("/invites/{invite_id}/resend", response_model=ParentInviteResponse)
async def resend_invite(
    invite_id: int,
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ParentService(db).resend_invite(parent, invite_id)


@router.delete("/{parent_id}", response_model=MessageResponse)
async def remove_parent(
    parent_id: int,
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ParentService(db).remove_parent(parent, parent_id)
