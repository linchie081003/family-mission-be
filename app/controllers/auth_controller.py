"""Controller: parent authentication (MVC)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_family
from app.core.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.models import Family
from app.schemas import FamilyLogin, FamilyPublic, FamilyRegister, RegisterResponse, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(
    data: FamilyRegister,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    check_rate_limit(request, "auth_register")
    return await AuthService(db).register(data)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: FamilyLogin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    check_rate_limit(request, "auth_login")
    return await AuthService(db).login(data)


@router.get("/me", response_model=FamilyPublic)
async def get_me(family: Annotated[Family, Depends(get_current_family)]):
    return family
