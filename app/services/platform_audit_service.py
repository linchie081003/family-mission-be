from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PlatformAuditLog

FEATURE_LABELS = {
    "quiz": "Quiz",
    "chat": "Chat",
    "agenda": "Agenda Keluarga",
}


async def log_platform_feature_change(
    db: AsyncSession,
    *,
    platform_admin_id: int,
    family_id: int,
    family_name: str,
    feature_key: str,
    enabled: bool,
    previous: bool,
) -> PlatformAuditLog:
    label = FEATURE_LABELS.get(feature_key, feature_key)
    action = "mengaktifkan" if enabled else "menonaktifkan"
    entry = PlatformAuditLog(
        platform_admin_id=platform_admin_id,
        family_id=family_id,
        feature_key=feature_key,
        enabled=enabled,
        summary=f"Super Admin {action} fitur {label} untuk keluarga {family_name}",
        details={
            "family_name": family_name,
            "feature_key": feature_key,
            "feature_label": label,
            "previous": previous,
            "current": enabled,
        },
    )
    db.add(entry)
    await db.flush()
    return entry
