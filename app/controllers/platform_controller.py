"""Controller: platform admin (MVC)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_platform_admin
from app.core.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.models import PlatformAdmin
from app.schemas import (
    PlatformAdminLogin,
    PlatformAdminProfileUpdate,
    PlatformAdminPublic,
    PlatformAuditLogPublic,
    PlatformFamilyFeaturesUpdate,
    PlatformFamilyPublic,
    PlatformNotificationPublic,
    QuizTemplateCreate,
    QuizTemplateDetailPublic,
    QuizTemplateUpdate,
    TokenResponse,
)
from app.services.platform_notification_service import PlatformNotificationService
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/auth/login", response_model=TokenResponse)
async def platform_login(
    data: PlatformAdminLogin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "platform_login")
    return await PlatformService(db).login(data)


@router.get("/auth/me", response_model=PlatformAdminPublic)
async def platform_me(admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)]):
    return admin


@router.patch("/auth/profile", response_model=PlatformAdminPublic)
async def update_platform_profile(
    data: PlatformAdminProfileUpdate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await PlatformService(db).update_profile(admin, data)


@router.get("/notifications", response_model=list[PlatformNotificationPublic])
async def list_platform_notifications(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    unread_only: bool = False,
):
    del admin
    return await PlatformNotificationService(db).list_notifications(limit=limit, unread_only=unread_only)


@router.get("/notifications/unread-count")
async def platform_notifications_unread_count(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    count = await PlatformNotificationService(db).unread_count()
    return {"count": count}


@router.post("/notifications/{notification_id}/read", response_model=PlatformNotificationPublic)
async def read_platform_notification(
    notification_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    notif = await PlatformNotificationService(db).mark_read(notification_id)
    if not notif:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return notif


@router.post("/notifications/read-all")
async def read_all_platform_notifications(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    count = await PlatformNotificationService(db).mark_all_read()
    return {"marked_read": count}


@router.post("/families/{family_id}/approve", response_model=PlatformFamilyPublic)
async def approve_family(
    family_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await PlatformService(db).approve_family(admin, family_id)
    from app.models.models import Child
    from sqlalchemy import func, select

    count = await db.scalar(
        select(func.count()).select_from(Child).where(Child.family_id == family.id, Child.is_active.is_(True))
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


@router.get("/families", response_model=list[PlatformFamilyPublic])
async def list_families(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    return await PlatformService(db).list_families()


@router.patch("/families/{family_id}/features", response_model=PlatformFamilyPublic)
async def update_family_features(
    family_id: int,
    data: PlatformFamilyFeaturesUpdate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await PlatformService(db).update_features(admin, family_id, data)
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.get("/audit", response_model=list[PlatformAuditLogPublic])
async def list_platform_audit(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 100,
):
    del admin
    return await PlatformService(db).list_audit(limit)


@router.get("/quiz-templates")
async def list_quiz_templates(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    from app.services.quiz_service import QuizService

    templates = await QuizService(db).list_all_templates_admin()
    return [
        {
            "id": t.id,
            "subject": t.subject,
            "title": t.title,
            "grade_level": t.grade_level,
            "is_active": t.is_active,
        }
        for t in templates
    ]


@router.get("/quiz-templates/{template_id}", response_model=QuizTemplateDetailPublic)
async def get_quiz_template(
    template_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    from app.services.quiz_service import QuizService

    return await QuizService(db).get_template(template_id)


@router.post("/quiz-templates", response_model=QuizTemplateDetailPublic)
async def create_quiz_template(
    data: QuizTemplateCreate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    from app.services.quiz_service import QuizService

    return await QuizService(db).create_template(data)


@router.put("/quiz-templates/{template_id}", response_model=QuizTemplateDetailPublic)
async def update_quiz_template(
    template_id: int,
    data: QuizTemplateUpdate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    from app.services.quiz_service import QuizService

    return await QuizService(db).update_template(template_id, data)


@router.delete("/quiz-templates/{template_id}")
async def delete_quiz_template(
    template_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    from app.services.quiz_service import QuizService

    return await QuizService(db).delete_template(template_id)


@router.patch("/quiz-templates/{template_id}/active")
async def toggle_quiz_template(
    template_id: int,
    is_active: bool,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    from app.services.quiz_service import QuizService

    tpl = await QuizService(db).set_template_active(template_id, is_active)
    return {"id": tpl.id, "is_active": tpl.is_active}


@router.get("/stats")
async def platform_stats(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    return await PlatformService(db).stats()
