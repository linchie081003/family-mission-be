"""Controller: parent audit logs (MVC)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_family
from app.core.database import get_db
from app.models.models import Family
from app.schemas import AuditLogPublic
from app.services.settings_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogPublic])
async def list_audit_logs(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=500),
):
    return await AuditService(db).list_parent_logs(family.id, limit)
