import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import TOKEN_INVALID
from app.core.database import get_db
from app.models.models import Child, Family, Parent, PlatformAdmin

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_pin(pin: str) -> str:
    return pwd_context.hash(pin)


def verify_pin(pin: str, hashed: str) -> bool:
    return pwd_context.verify(pin, hashed)


def generate_family_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID) from exc


async def get_current_parent(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Parent:
    payload = decode_access_token(credentials.credentials)
    parent_id = payload.get("parent_id")
    family_id = payload.get("family_id")
    role = payload.get("role")
    if parent_id is None or family_id is None or role != "parent":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)

    result = await db.execute(
        select(Parent).where(Parent.id == parent_id, Parent.family_id == family_id, Parent.is_active == True)
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)

    family = await db.get(Family, family_id)
    if not family or not family.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun keluarga dinonaktifkan. Hubungi support jika perlu bantuan.",
        )
    if not parent.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email belum diverifikasi. Cek inbox atau minta kirim ulang verifikasi.",
        )
    return parent


async def get_current_family(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Family:
    parent = await get_current_parent(credentials, db)
    family = await db.get(Family, parent.family_id)
    if not family:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)
    return family


async def get_current_child(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Child:
    payload = decode_access_token(credentials.credentials)
    child_id = payload.get("child_id")
    role = payload.get("role")
    if child_id is None or role != "child":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)

    result = await db.execute(select(Child).where(Child.id == child_id, Child.is_active == True))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)
    return child


async def get_current_platform_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformAdmin:
    payload = decode_access_token(credentials.credentials)
    admin_id = payload.get("platform_admin_id")
    role = payload.get("role")
    if admin_id is None or role != "platform_admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)

    result = await db.execute(select(PlatformAdmin).where(PlatformAdmin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=TOKEN_INVALID)
    return admin
