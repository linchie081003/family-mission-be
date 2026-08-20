"""Controller: parent authentication (MVC)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_family, get_current_parent
from app.core.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.models import Family, Parent
from app.schemas import (
    FamilyLogin,
    FamilyPublic,
    FamilyRegister,
    ForgotPasswordRequest,
    MessageResponse,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(
    data: FamilyRegister,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "auth_register")
    result = await AuthService(db).register(data)
    return result


@router.post("/login", response_model=TokenResponse)
async def login(
    data: FamilyLogin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "auth_login")
    return await AuthService(db).login(data)


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Query(...),
):
    await check_rate_limit(request, "verify_email")
    return await AuthService(db).verify_email(token)


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: ResendVerificationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "verify_email")
    return await AuthService(db).resend_verification(data)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "forgot_password")
    return await AuthService(db).forgot_password(data)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "forgot_password")
    return await AuthService(db).reset_password(data)


@router.get("/me", response_model=FamilyPublic)
async def get_me(family: Annotated[Family, Depends(get_current_family)]):
    return family


@router.get("/me/parent", response_model=dict)
async def get_me_parent(parent: Annotated[Parent, Depends(get_current_parent)]):
    return {
        "id": parent.id,
        "email": parent.email,
        "name": parent.name,
        "role": parent.role.value,
        "family_id": parent.family_id,
    }
