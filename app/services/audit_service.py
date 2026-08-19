from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog


async def log_audit(
    db: AsyncSession,
    family_id: int,
    actor_role: str,
    actor_label: str,
    action: str,
    entity_type: str,
    summary: str,
    entity_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        family_id=family_id,
        actor_role=actor_role,
        actor_label=actor_label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details=details,
    )
    db.add(entry)
    await db.flush()
    return entry
