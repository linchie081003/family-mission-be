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
                "rewards_enabled": family.rewards_enabled,
                "mission_evidence_enabled": family.mission_evidence_enabled,
                "daily_mission_limit": family.daily_mission_limit,
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
        from app.models.models import Child

        count = await self.db.scalar(
            select(func.count()).select_from(Child).where(
                Child.family_id == family.id,
                Child.is_active.is_(True),
            )
        )
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
        }

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
