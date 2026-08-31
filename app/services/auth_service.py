import logging
import os
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, hash_password, verify_password
from app.core.config import settings
from app.core.constants import AUTH_INVALID_CREDENTIALS
from app.core.tokens import generate_raw_token, hash_token, utcnow
from app.models.models import (
    BadgeDefinition,
    EmailTokenPurpose,
    Family,
    Mission,
    MissionCategory,
    MissionDifficulty,
    ParentRole,
    Punishment,
    Reward,
)
from app.repositories.email_token_repository import EmailTokenRepository
from app.repositories.family_repository import FamilyRepository
from app.repositories.parent_repository import ParentRepository
from app.schemas import (
    FamilyLogin,
    FamilyRegister,
    ForgotPasswordRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResendVerificationRequest,
    TokenResponse,
)
from app.services.email_service import send_verification_email, send_password_reset_email
from app.services.gamification import DEFAULT_BADGES, DEFAULT_MISSIONS, DEFAULT_PUNISHMENTS, DEFAULT_REWARDS
from fastapi import HTTPException
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def send_verification_for_parent(db: AsyncSession, parent_id: int, email: str) -> None:
    tokens = EmailTokenRepository(db)
    raw = generate_raw_token()
    await tokens.invalidate_unused(parent_id, EmailTokenPurpose.VERIFY_EMAIL)
    await tokens.create(
        parent_id=parent_id,
        token_hash=hash_token(raw),
        purpose=EmailTokenPurpose.VERIFY_EMAIL,
        expires_at=utcnow() + timedelta(hours=settings.email_token_expire_hours),
    )
    link = f"{settings.frontend_base_url}/verify-email?token={raw}"
    sent = await send_verification_email(to=email, link=link)
    if not sent:
        logger.info("DEV verify email for %s: %s", email, link)


class AuthService:
    """Business logic: parent registration & authentication."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.families = FamilyRepository(db)
        self.parents = ParentRepository(db)
        self.tokens = EmailTokenRepository(db)

    async def _seed_defaults(self, family: Family) -> None:
        if family.rewards_enabled:
            for code, name, desc, icon, min_pts in DEFAULT_BADGES:
                existing = await self.db.execute(select(BadgeDefinition).where(BadgeDefinition.code == code))
                if not existing.scalar_one_or_none():
                    self.db.add(BadgeDefinition(code=code, name=name, description=desc, icon=icon, min_lifetime_points=min_pts))

        for title, cat, pts, diff in DEFAULT_MISSIONS:
            self.db.add(Mission(
                family_id=family.id, title=title, category=MissionCategory(cat),
                points=pts, difficulty=MissionDifficulty(diff),
            ))
        if family.rewards_enabled:
            for title, pts in DEFAULT_PUNISHMENTS:
                self.db.add(Punishment(family_id=family.id, title=title, points_deducted=pts))
            for title, desc, cost in DEFAULT_REWARDS:
                self.db.add(Reward(family_id=family.id, title=title, description=desc, points_cost=cost))

    async def _send_verification(self, parent_id: int, email: str) -> None:
        await send_verification_for_parent(self.db, parent_id, email)

    async def register(self, data: FamilyRegister) -> RegisterResponse:
        if await self.parents.email_exists(data.email):
            raise HTTPException(status_code=400, detail="Email sudah terdaftar")

        referred_by_id = None
        if data.referral_code:
            referrer = await self.families.get_by_referral_code(data.referral_code)
            if referrer:
                referred_by_id = referrer.id

        now = utcnow()
        family = await self.families.create(
            email=data.email,
            password=data.password,
            family_name=data.family_name,
            is_active=True,
            referred_by_family_id=referred_by_id,
        )
        parent = await self.parents.create(
            family_id=family.id,
            email=data.email,
            password=data.password,
            name=data.name,
            role=data.role,
            is_primary=True,
            email_verified=False,
            terms_accepted_at=now,
            privacy_accepted_at=now,
            parental_consent_at=now,
            child_data_protection_accepted_at=now,
            legal_doc_version=settings.legal_doc_version,
        )
        await self._seed_defaults(family)
        if os.getenv("TESTING", "").lower() in ("1", "true", "yes"):
            parent.email_verified = True
        await self._send_verification(parent.id, parent.email)
        from app.services.platform_notification_service import PlatformNotificationService

        await PlatformNotificationService(self.db).notify_family_registration(family)
        from app.services.subscription_service import SubscriptionService

        await SubscriptionService(self.db).start_trial(family, plan_slug="family", days=10)
        if referred_by_id and data.referral_code:
            from app.models.models import ReferralInvite
            invite_result = await self.db.execute(
                select(ReferralInvite).where(
                    ReferralInvite.referrer_family_id == referred_by_id,
                    ReferralInvite.invitee_email == data.email.lower(),
                    ReferralInvite.accepted_at.is_(None),
                )
            )
            invite = invite_result.scalar_one_or_none()
            if invite:
                invite.accepted_at = now
        await self.db.commit()

        return RegisterResponse(
            status="pending_verification",
            message="Pendaftaran berhasil. Cek email untuk verifikasi akun sebelum login.",
            family_id=family.id,
        )

    async def login(self, data: FamilyLogin) -> TokenResponse:
        parent = await self.parents.get_by_email(data.email)
        if not parent or not verify_password(data.password, parent.password_hash):
            raise HTTPException(status_code=401, detail=AUTH_INVALID_CREDENTIALS)
        if not parent.email_verified:
            raise HTTPException(
                status_code=403,
                detail="Email belum diverifikasi. Cek inbox atau minta kirim ulang verifikasi.",
            )
        if not parent.is_active:
            raise HTTPException(status_code=403, detail="Akun dinonaktifkan.")
        family = await self.families.get_by_id(parent.family_id)
        if not family or not family.is_active:
            raise HTTPException(status_code=403, detail="Akun keluarga dinonaktifkan.")

        from app.services.subscription_service import SubscriptionService

        await SubscriptionService(self.db).check_and_expire_trials(family.id)

        token = create_access_token({
            "parent_id": parent.id,
            "family_id": family.id,
            "role": "parent",
            "parent_role": parent.role.value,
        })
        return TokenResponse(
            access_token=token,
            role="parent",
            family_id=family.id,
            parent_id=parent.id,
            parent_role=parent.role.value,
        )

    async def verify_email(self, raw_token: str) -> dict:
        token = await self.tokens.find_valid(hash_token(raw_token), EmailTokenPurpose.VERIFY_EMAIL)
        if not token:
            raise HTTPException(status_code=400, detail="Token tidak valid atau sudah kedaluwarsa")
        parent = await self.parents.get_by_id(token.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Token tidak valid")
        parent.email_verified = True
        await self.tokens.mark_used(token)
        await self.db.commit()
        return {"message": "Email berhasil diverifikasi. Silakan login."}

    async def resend_verification(self, data: ResendVerificationRequest) -> dict:
        parent = await self.parents.get_by_email(data.email)
        if parent and not parent.email_verified:
            await self._send_verification(parent.id, parent.email)
            await self.db.commit()
        return {"message": "Jika email terdaftar dan belum diverifikasi, link verifikasi telah dikirim."}

    async def forgot_password(self, data: ForgotPasswordRequest) -> dict:
        parent = await self.parents.get_by_email(data.email)
        if parent and parent.is_active:
            raw = generate_raw_token()
            await self.tokens.invalidate_unused(parent.id, EmailTokenPurpose.RESET_PASSWORD)
            await self.tokens.create(
                parent_id=parent.id,
                token_hash=hash_token(raw),
                purpose=EmailTokenPurpose.RESET_PASSWORD,
                expires_at=utcnow() + timedelta(minutes=settings.reset_token_expire_minutes),
            )
            link = f"{settings.frontend_base_url}/reset-password?token={raw}"
            sent = await send_password_reset_email(to=parent.email, link=link)
            if not sent:
                logger.info("DEV reset password for %s: %s", parent.email, link)
            await self.db.commit()
        return {"message": "Jika email terdaftar, link reset password telah dikirim."}

    async def reset_password(self, data: ResetPasswordRequest) -> dict:
        token = await self.tokens.find_valid(hash_token(data.token), EmailTokenPurpose.RESET_PASSWORD)
        if not token:
            raise HTTPException(status_code=400, detail="Token tidak valid atau sudah kedaluwarsa")
        parent = await self.parents.get_by_id(token.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Token tidak valid")
        parent.password_hash = hash_password(data.new_password)
        await self.tokens.mark_used(token)
        await self.db.commit()
        return {"message": "Password berhasil diubah. Silakan login."}
