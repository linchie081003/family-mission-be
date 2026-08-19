from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.core.constants import AUTH_INVALID_CREDENTIALS
from app.models.models import Family, PlatformAdmin, PlatformAuditLog
from app.repositories.platform_repository import PlatformRepository
from app.schemas import PlatformAdminLogin, PlatformAdminProfileUpdate, PlatformFamilyFeaturesUpdate, TokenResponse
from app.services.platform_audit_service import FEATURE_LABELS, log_platform_feature_change
from app.services.platform_notification_service import PlatformNotificationService

FEATURE_FIELDS = ("quiz_enabled", "chat_enabled", "agenda_enabled", "is_active")


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

    async def list_families(self) -> list[dict]:
        from app.models.models import Child

        result = await self.db.execute(select(Family).order_by(Family.created_at.desc()))
        families = list(result.scalars().all())
        items = []
        for family in families:
            count = await self.db.scalar(
                select(func.count()).select_from(Child).where(
                    Child.family_id == family.id,
                    Child.is_active.is_(True),
                )
            )
            items.append({
                "id": family.id,
                "email": family.email,
                "family_name": family.family_name,
                "family_code": family.family_code,
                "quiz_enabled": family.quiz_enabled,
                "chat_enabled": family.chat_enabled,
                "agenda_enabled": family.agenda_enabled,
                "is_active": family.is_active,
                "children_count": count or 0,
                "created_at": family.created_at,
            })
        return items

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
            feature_key = "tenant_active" if field == "is_active" else field.replace("_enabled", "")
            await log_platform_feature_change(
                self.db,
                platform_admin_id=admin.id,
                family_id=family.id,
                family_name=family.family_name,
                feature_key=feature_key,
                enabled=new_value,
                previous=previous,
            )

        await self.db.flush()
        return family

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
        enabled_counts = {}
        for field in FEATURE_FIELDS:
            count = await self.db.scalar(
                select(func.count()).select_from(Family).where(getattr(Family, field).is_(True))
            )
            enabled_counts[field] = count or 0
        notif_service = PlatformNotificationService(self.db)
        # #region agent log
        from app.core.debug_log import debug_log
        debug_log(
            location="platform_service.py:stats",
            message="Platform stats loaded",
            data={"families_total": families_count, "families_pending": pending_count},
            hypothesis_id="A",
        )
        # #endregion
        return {
            "families_total": families_count,
            "families_pending": pending_count,
            "platform_notifications_unread": await notif_service.unread_count(),
            "features_enabled": enabled_counts,
            "feature_labels": FEATURE_LABELS,
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
