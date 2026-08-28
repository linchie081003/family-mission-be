from typing import Literal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.core.config import settings
from app.core.constants import AUTH_INVALID_CREDENTIALS
from app.core.tokens import utcnow
from app.models.models import EmailTokenPurpose, Family, Parent, PlatformAdmin, PlatformAuditLog
from app.repositories.email_token_repository import EmailTokenRepository
from app.repositories.platform_repository import PlatformRepository
from app.schemas import PlatformAdminLogin, PlatformAdminProfileUpdate, PlatformFamilyFeaturesUpdate, TokenResponse
from app.services.activation_presets import PRESET_LABELS, ActivationPresetKey, get_preset
from app.services.auth_service import send_verification_for_parent
from app.services.email_service import send_tenant_activation_email
from app.services.platform_audit_service import FEATURE_LABELS, log_platform_feature_change
from app.services.platform_notification_service import PlatformNotificationService

FEATURE_TOGGLE_FIELDS = (
    "quiz_enabled",
    "chat_enabled",
    "agenda_enabled",
    "rewards_enabled",
    "mission_evidence_enabled",
    "is_active",
)
FEATURE_FIELDS = FEATURE_TOGGLE_FIELDS + ("daily_mission_limit",)


def _feature_key_for_field(field: str) -> str:
    if field == "is_active":
        return "tenant_active"
    if field == "daily_mission_limit":
        return "daily_mission_limit"
    return field.replace("_enabled", "")


class PlatformService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.platform = PlatformRepository(db)

    async def login(self, data: PlatformAdminLogin) -> TokenResponse:
        admin = await self.platform.verify_credentials(data.email, data.password)
        if not admin:
            raise HTTPException(status_code=401, detail=AUTH_INVALID_CREDENTIALS)
        token = create_access_token({"platform_admin_id": admin.id, "role": "platform_admin"})
        return TokenResponse(access_token=token, role="platform_admin")

    def _family_query_base(self):
        from app.models.models import Child

        return select(Family).order_by(Family.created_at.desc())

    async def _family_to_dict(self, family: Family) -> dict:
        from app.models.models import Child

        count = await self.db.scalar(
            select(func.count()).select_from(Child).where(
                Child.family_id == family.id,
                Child.is_active.is_(True),
            )
        )
        referrer_name = None
        if family.referred_by_family_id:
            referrer = await self.db.get(Family, family.referred_by_family_id)
            if referrer:
                referrer_name = referrer.family_name

        primary = await self.db.scalar(
            select(Parent).where(Parent.family_id == family.id, Parent.is_primary.is_(True))
        )
        email_verified = bool(primary and primary.email_verified)

        return {
            "id": family.id,
            "email": family.email,
            "family_name": family.family_name,
            "family_code": family.family_code,
            "quiz_enabled": family.quiz_enabled,
            "chat_enabled": family.chat_enabled,
            "agenda_enabled": family.agenda_enabled,
            "rewards_enabled": family.rewards_enabled,
            "mission_evidence_enabled": family.mission_evidence_enabled,
            "daily_mission_limit": family.daily_mission_limit,
            "is_active": family.is_active,
            "children_count": count or 0,
            "created_at": family.created_at,
            "activated_at": family.activated_at,
            "activation_preset": family.activation_preset,
            "email_verified": email_verified,
            "referral_code": family.referral_code,
            "referrer_name": referrer_name,
        }

    async def _get_primary_parent(self, family_id: int) -> Parent | None:
        return await self.db.scalar(
            select(Parent).where(Parent.family_id == family_id, Parent.is_primary.is_(True))
        )

    async def list_families(
        self,
        *,
        search: str = "",
        status: Literal["all", "active", "inactive"] = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        q = select(Family)
        count_q = select(func.count()).select_from(Family)

        if search.strip():
            term = f"%{search.strip()}%"
            filt = or_(
                Family.family_name.ilike(term),
                Family.email.ilike(term),
                Family.family_code.ilike(term),
            )
            q = q.where(filt)
            count_q = count_q.where(filt)

        if status == "active":
            q = q.where(Family.is_active.is_(True))
            count_q = count_q.where(Family.is_active.is_(True))
        elif status == "inactive":
            q = q.where(Family.is_active.is_(False))
            count_q = count_q.where(Family.is_active.is_(False))

        total = await self.db.scalar(count_q) or 0
        q = q.order_by(Family.created_at.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0))
        result = await self.db.execute(q)
        families = list(result.scalars().all())
        items = []
        for family in families:
            items.append(await self._family_to_dict(family))
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def list_pending_activation(self, *, limit: int = 50, offset: int = 0) -> dict:
        q = (
            select(Family)
            .where(Family.activated_at.is_(None))
            .order_by(Family.created_at.desc())
            .limit(min(max(limit, 1), 200))
            .offset(max(offset, 0))
        )
        count_q = select(func.count()).select_from(Family).where(Family.activated_at.is_(None))
        total = await self.db.scalar(count_q) or 0
        result = await self.db.execute(q)
        families = list(result.scalars().all())
        items = [await self._family_to_dict(f) for f in families]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def pending_activation_count(self) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(Family).where(Family.activated_at.is_(None))
        ) or 0

    async def activate_family(
        self,
        admin: PlatformAdmin,
        family_id: int,
        preset: ActivationPresetKey,
    ) -> Family:
        family = await self.db.get(Family, family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        features = get_preset(preset)
        for field, value in features.items():
            setattr(family, field, value)
        family.activated_at = utcnow()
        family.activation_preset = preset

        label = PRESET_LABELS[preset]
        primary = await self._get_primary_parent(family.id)
        welcome_email_sent = False
        if primary:
            welcome_email_sent = await send_tenant_activation_email(
                to=primary.email,
                family_name=family.family_name,
                preset_label=label,
                login_url=f"{settings.frontend_base_url}/login",
            )

        entry = PlatformAuditLog(
            platform_admin_id=admin.id,
            family_id=family.id,
            feature_key=f"activation_{preset}",
            enabled=True,
            summary=f"Super Admin mengaktifkan preset {label} untuk keluarga {family.family_name}",
            details={
                "family_name": family.family_name,
                "preset": preset,
                "features": features,
                "welcome_email_sent": welcome_email_sent,
            },
        )
        self.db.add(entry)
        await self.db.flush()
        return family

    async def resend_verification(
        self,
        admin: PlatformAdmin,
        family_id: int,
    ) -> Family:
        family = await self.db.get(Family, family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        parent = await self._get_primary_parent(family.id)
        if not parent:
            raise HTTPException(status_code=404, detail="Orang tua utama tidak ditemukan")
        if parent.email_verified:
            raise HTTPException(status_code=400, detail="Email sudah diverifikasi")

        await send_verification_for_parent(self.db, parent.id, parent.email)
        entry = PlatformAuditLog(
            platform_admin_id=admin.id,
            family_id=family.id,
            feature_key="resend_verification",
            enabled=True,
            summary=f"Super Admin mengirim ulang email verifikasi untuk {family.family_name}",
            details={"family_name": family.family_name, "email": parent.email},
        )
        self.db.add(entry)
        await self.db.flush()
        return family

    async def manual_verify_email(
        self,
        admin: PlatformAdmin,
        family_id: int,
    ) -> Family:
        family = await self.db.get(Family, family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        parent = await self._get_primary_parent(family.id)
        if not parent:
            raise HTTPException(status_code=404, detail="Orang tua utama tidak ditemukan")
        if parent.email_verified:
            raise HTTPException(status_code=400, detail="Email sudah diverifikasi")

        parent.email_verified = True
        tokens = EmailTokenRepository(self.db)
        await tokens.invalidate_unused(parent.id, EmailTokenPurpose.VERIFY_EMAIL)
        entry = PlatformAuditLog(
            platform_admin_id=admin.id,
            family_id=family.id,
            feature_key="manual_verify_email",
            enabled=True,
            summary=f"Super Admin verifikasi email manual untuk {family.family_name}",
            details={"family_name": family.family_name, "email": parent.email},
        )
        self.db.add(entry)
        await self.db.flush()
        return family

    async def update_features(
        self,
        admin: PlatformAdmin,
        family_id: int,
        data: PlatformFamilyFeaturesUpdate,
    ) -> Family:
        family = await self.db.get(Family, family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return family

        for field in FEATURE_FIELDS:
            if field not in updates:
                continue
            new_value = updates[field]
            previous = getattr(family, field)
            if previous == new_value:
                continue
            setattr(family, field, new_value)
            if field == "daily_mission_limit":
                label = FEATURE_LABELS.get("daily_mission_limit", "Batas misi harian")
                entry = PlatformAuditLog(
                    platform_admin_id=admin.id,
                    family_id=family.id,
                    feature_key="daily_mission_limit",
                    enabled=new_value is not None,
                    summary=(
                        f"Super Admin mengubah {label} untuk keluarga {family.family_name}: "
                        f"{previous if previous is not None else 'unlimited'} → "
                        f"{new_value if new_value is not None else 'unlimited'}"
                    ),
                    details={
                        "family_name": family.family_name,
                        "feature_key": "daily_mission_limit",
                        "previous": previous,
                        "current": new_value,
                    },
                )
                self.db.add(entry)
                await self.db.flush()
                continue
            feature_key = _feature_key_for_field(field)
            await log_platform_feature_change(
                self.db,
                platform_admin_id=admin.id,
                family_id=family.id,
                family_name=family.family_name,
                feature_key=feature_key,
                enabled=bool(new_value),
                previous=bool(previous),
            )

        await self.db.flush()
        return family

    async def family_public_item(self, family: Family) -> dict:
        return await self._family_to_dict(family)

    async def list_audit(self, limit: int = 100) -> list[PlatformAuditLog]:
        result = await self.db.execute(
            select(PlatformAuditLog)
            .order_by(PlatformAuditLog.created_at.desc())
            .limit(min(max(limit, 1), 500))
        )
        return list(result.scalars().all())

    async def stats(self) -> dict:
        families_count = await self.db.scalar(select(func.count()).select_from(Family)) or 0
        pending_count = await self.db.scalar(
            select(func.count()).select_from(Family).where(Family.is_active.is_(False))
        ) or 0
        pending_activation = await self.pending_activation_count()
        enabled_counts = {}
        for field in FEATURE_TOGGLE_FIELDS:
            count = await self.db.scalar(
                select(func.count()).select_from(Family).where(getattr(Family, field).is_(True))
            )
            enabled_counts[field] = count or 0
        limited_count = await self.db.scalar(
            select(func.count()).select_from(Family).where(Family.daily_mission_limit.is_not(None))
        ) or 0
        enabled_counts["daily_mission_limit"] = limited_count
        notif_service = PlatformNotificationService(self.db)
        return {
            "families_total": families_count,
            "families_pending": pending_count,
            "pending_activation_count": pending_activation,
            "platform_notifications_unread": await notif_service.unread_count(),
            "features_enabled": enabled_counts,
            "feature_labels": {
                **FEATURE_LABELS,
                "daily_mission_limit": "Batas misi harian",
                "quiz_enabled": "Quiz",
                "chat_enabled": "Chat",
                "agenda_enabled": "Agenda Keluarga",
                "rewards_enabled": "Reward & Poin",
                "mission_evidence_enabled": "Bukti Misi",
                "is_active": "Tenant Aktif",
            },
        }

    async def update_profile(self, admin: PlatformAdmin, data: PlatformAdminProfileUpdate) -> PlatformAdmin:
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates and updates["name"] is not None:
            admin.name = updates["name"].strip()
        if "notification_email" in updates:
            val = updates["notification_email"]
            admin.notification_email = str(val) if val else None
        await self.db.flush()
        return admin

    async def approve_family(self, admin: PlatformAdmin, family_id: int) -> Family:
        return await self.update_features(
            admin,
            family_id,
            PlatformFamilyFeaturesUpdate(is_active=True),
        )
