"""Controller: child authentication (MVC)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_child, get_current_family
from app.core.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.models import Child, Family
from app.schemas import ChildListItem, ChildLoginSelect, ChildPinChange, ChildSetPin, TokenResponse
from app.services.child_auth_service import ChildAuthService

router = APIRouter(prefix="/child-auth", tags=["child-auth"])


@router.get("/family/{family_code}/children", response_model=list[ChildListItem])
async def list_children_for_login(
    family_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "child_lookup")
    return await ChildAuthService(db).list_children_for_login(family_code)


@router.post("/login", response_model=TokenResponse)
async def child_login(
    data: ChildLoginSelect,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "child_login")
    return await ChildAuthService(db).login(data)


@router.get("/me")
async def child_me(child: Annotated[Child, Depends(get_current_child)]):
    return {"id": child.id, "name": child.name, "family_id": child.family_id}


@router.post("/first-time-setup", response_model=TokenResponse)
async def first_time_setup(
    data: ChildLoginSelect,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "child_setup")
    return await ChildAuthService(db).first_time_setup(data)


@router.post("/setup-pin")
async def setup_pin(
    data: ChildSetPin,
    db: Annotated[AsyncSession, Depends(get_db)],
    child: Annotated[Child, Depends(get_current_child)],
):
    return await ChildAuthService(db).setup_pin(child, data)


@router.post("/change-pin")
async def change_pin(
    data: ChildPinChange,
    db: Annotated[AsyncSession, Depends(get_db)],
    child: Annotated[Child, Depends(get_current_child)],
):
    return await ChildAuthService(db).change_pin(child, data)


@router.post("/{child_id}/reset-pin")
async def reset_pin(
    child_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    family: Annotated[Family, Depends(get_current_family)],
):
    return await ChildAuthService(db).reset_pin(family, child_id)
