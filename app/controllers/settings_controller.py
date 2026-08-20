"""Controller: family settings (MVC)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_family, get_current_parent
from app.core.database import get_db
from app.models.models import Family, Parent
from app.schemas import FamilyPublic, ParentPasswordChange, SettingsHistoryPublic, SettingsUpdate
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=FamilyPublic)
async def get_settings(family: Annotated[Family, Depends(get_current_family)]):
    return family


@router.patch("", response_model=FamilyPublic)
async def update_settings(
    data: SettingsUpdate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await SettingsService(db).update_settings(family, data)


@router.post("/change-password")
async def change_parent_password(
    data: ParentPasswordChange,
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await SettingsService(db).change_password(parent, data)


@router.get("/history", response_model=list[SettingsHistoryPublic])
async def settings_history(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await SettingsService(db).get_history(family.id)
