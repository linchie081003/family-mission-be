from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, verify_password
from app.core.constants import AUTH_INVALID_CREDENTIALS
from app.models.models import BadgeDefinition, Family, Mission, MissionCategory, MissionDifficulty, Punishment, Reward
from app.repositories.family_repository import FamilyRepository
from app.schemas import FamilyLogin, FamilyRegister, RegisterResponse, TokenResponse
from app.services.gamification import DEFAULT_BADGES, DEFAULT_MISSIONS, DEFAULT_PUNISHMENTS, DEFAULT_REWARDS
from app.services.platform_notification_service import PlatformNotificationService
from fastapi import HTTPException


class AuthService:
    """Business logic: parent registration & authentication."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.families = FamilyRepository(db)

    async def _seed_defaults(self, family: Family) -> None:
        for code, name, desc, icon, min_pts in DEFAULT_BADGES:
            existing = await self.db.execute(select(BadgeDefinition).where(BadgeDefinition.code == code))
            if not existing.scalar_one_or_none():
                self.db.add(BadgeDefinition(code=code, name=name, description=desc, icon=icon, min_lifetime_points=min_pts))

        for title, cat, pts, diff in DEFAULT_MISSIONS:
            self.db.add(Mission(
                family_id=family.id, title=title, category=MissionCategory(cat),
                points=pts, difficulty=MissionDifficulty(diff),
            ))
        for title, pts in DEFAULT_PUNISHMENTS:
            self.db.add(Punishment(family_id=family.id, title=title, points_deducted=pts))
        for title, desc, cost in DEFAULT_REWARDS:
            self.db.add(Reward(family_id=family.id, title=title, description=desc, points_cost=cost))

    async def register(self, data: FamilyRegister) -> RegisterResponse:
        if await self.families.email_exists(data.email):
            raise HTTPException(status_code=400, detail="Email sudah terdaftar")

        family = await self.families.create(
            email=data.email,
            password=data.password,
            family_name=data.family_name,
            is_active=False,
        )
        await self._seed_defaults(family)
        await PlatformNotificationService(self.db).notify_family_registration(family)
        return RegisterResponse(
            status="pending",
            message="Pendaftaran berhasil. Menunggu persetujuan Super Admin sebelum bisa login.",
            family_id=family.id,
        )

    async def login(self, data: FamilyLogin) -> TokenResponse:
        family = await self.families.get_by_email(data.email)
        if not family or not verify_password(data.password, family.password_hash):
            raise HTTPException(status_code=401, detail=AUTH_INVALID_CREDENTIALS)
        if not family.is_active:
            raise HTTPException(
                status_code=403,
                detail="Akun belum disetujui Super Admin atau dinonaktifkan. Hubungi admin jika sudah mendaftar.",
            )

        token = create_access_token({"family_id": family.id, "role": "parent"})
        return TokenResponse(access_token=token, role="parent", family_id=family.id)
