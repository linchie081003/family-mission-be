"""Controller: platform admin (MVC)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_platform_admin
from app.core.database import get_db
from app.core.upload_url import get_upload_url
from app.middleware.rate_limit import check_rate_limit
from app.models.models import PlatformAdmin
from app.schemas import (
    BillingStatsPublic,
    ManualPaymentCreate,
    PaymentListResponse,
    PaymentRejectRequest,
    PaymentSettingsPublic,
    PaymentSettingsUpdate,
    PlanCreate,
    PlanPublic,
    PlanUpdate,
    PlatformAdminLogin,
    PlatformAdminProfileUpdate,
    PlatformAdminPublic,
    PlatformAuditLogPublic,
    PlatformBroadcastCreate,
    PlatformBroadcastPublic,
    PlatformFamilyActivate,
    PlatformFamilyAssignPlan,
    PlatformFamilyFeaturesUpdate,
    PlatformFamilyListResponse,
    PlatformFamilyPublic,
    PlatformNotificationPublic,
    PlatformReferralActivity,
    PlatformReferralLeaderboardEntry,
    PlatformReferralStats,
    QuizTemplateCreate,
    QuizTemplateDetailPublic,
    QuizTemplateUpdate,
    TokenResponse,
    TrialExtendRequest,
    TrialListResponse,
)
from app.services.platform_billing_service import PlatformBillingService
from app.services.platform_notification_service import PlatformNotificationService
from app.services.platform_referral_service import PlatformReferralService
from app.services.platform_service import PlatformService
from fastapi import File, UploadFile

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
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.get("/families/pending-activation/count")
async def pending_activation_count(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    count = await PlatformService(db).pending_activation_count()
    return {"count": count}


@router.get("/families/pending-activation", response_model=PlatformFamilyListResponse)
async def list_pending_activation(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
):
    del admin
    return await PlatformService(db).list_pending_activation(limit=limit, offset=offset)


@router.post("/families/{family_id}/activate", response_model=PlatformFamilyPublic)
async def activate_family(
    family_id: int,
    data: PlatformFamilyActivate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await PlatformService(db).activate_family(admin, family_id, data.preset)
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.post("/families/{family_id}/assign-plan", response_model=PlatformFamilyPublic)
async def assign_family_plan(
    family_id: int,
    data: PlatformFamilyAssignPlan,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not data.is_demo:
        raise HTTPException(status_code=400, detail="Endpoint ini khusus assign paket demo")
    family = await PlatformService(db).assign_demo_plan(
        admin, family_id, data.plan_slug, note=data.note
    )
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.post("/families/{family_id}/revoke-demo", response_model=PlatformFamilyPublic)
async def revoke_family_demo(
    family_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await PlatformService(db).revoke_demo(admin, family_id)
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.post("/families/{family_id}/resend-verification", response_model=PlatformFamilyPublic)
async def resend_family_verification(
    family_id: int,
    request: Request,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "verify_email")
    family = await PlatformService(db).resend_verification(admin, family_id)
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.post("/families/{family_id}/coparent-invites/{invite_id}/resend")
async def platform_resend_coparent_invite(
    family_id: int,
    invite_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.services.parent_service import ParentService

    result = await ParentService(db).resend_invite_for_family(family_id, invite_id)
    await db.commit()
    return result


@router.get("/families/{family_id}/coparent-invites/pending")
async def platform_list_pending_coparent_invites(
    family_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.repositories.parent_repository import ParentRepository
    from app.services.parent_service import ParentService

    primary = await ParentRepository(db).get_primary(family_id)
    if not primary:
        return []
    return await ParentService(db).list_pending_invites(primary)


@router.post("/families/{family_id}/verify-email", response_model=PlatformFamilyPublic)
async def manual_verify_family_email(
    family_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    family = await PlatformService(db).manual_verify_email(admin, family_id)
    await db.commit()
    return await PlatformService(db).family_public_item(family)


@router.get("/families", response_model=PlatformFamilyListResponse)
async def list_families(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str = "",
    status: Literal["all", "active", "inactive"] = "all",
    limit: int = 50,
    offset: int = 0,
):
    del admin
    return await PlatformService(db).list_families(
        search=search, status=status, limit=limit, offset=offset
    )


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


@router.get("/referrals/stats", response_model=PlatformReferralStats)
async def platform_referral_stats(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    return await PlatformReferralService(db).stats()


@router.get("/referrals/leaderboard", response_model=list[PlatformReferralLeaderboardEntry])
async def platform_referral_leaderboard(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
):
    del admin
    return await PlatformReferralService(db).leaderboard(limit=limit)


@router.get("/referrals/activity", response_model=list[PlatformReferralActivity])
async def platform_referral_activity(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
):
    del admin
    return await PlatformReferralService(db).activity(limit=limit)


@router.post("/broadcasts", response_model=PlatformBroadcastPublic)
async def create_broadcast(
    data: PlatformBroadcastCreate,
    request: Request,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await check_rate_limit(request, "platform_broadcast")
    record = await PlatformNotificationService(db).broadcast_to_families(
        admin, title=data.title, body=data.body, also_send_email=data.send_email
    )
    await db.commit()
    return record


@router.get("/broadcasts", response_model=list[PlatformBroadcastPublic])
async def list_broadcasts(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
):
    del admin
    return await PlatformNotificationService(db).list_broadcasts(limit=limit)


@router.get("/billing/stats", response_model=BillingStatsPublic)
async def billing_stats(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    return await PlatformBillingService(db).billing_stats()


@router.get("/plans", response_model=list[PlanPublic])
async def list_plans(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    svc = PlatformBillingService(db)
    plans = await svc.list_plans()
    result = []
    for plan in plans:
        item = PlanPublic.model_validate(plan)
        item.subscriber_count = await svc.plan_subscriber_count(plan.id)
        result.append(item)
    return result


@router.post("/plans", response_model=PlanPublic)
async def create_plan(
    data: PlanCreate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    plan = await PlatformBillingService(db).create_plan(data.model_dump())
    await db.commit()
    item = PlanPublic.model_validate(plan)
    item.subscriber_count = 0
    return item


@router.put("/plans/{plan_id}", response_model=PlanPublic)
async def update_plan(
    plan_id: int,
    data: PlanUpdate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    svc = PlatformBillingService(db)
    plan = await svc.update_plan(plan_id, data.model_dump(exclude_unset=True))
    await db.commit()
    item = PlanPublic.model_validate(plan)
    item.subscriber_count = await svc.plan_subscriber_count(plan.id)
    return item


@router.patch("/plans/{plan_id}/active", response_model=PlanPublic)
async def toggle_plan_active(
    plan_id: int,
    is_active: bool,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    svc = PlatformBillingService(db)
    plan = await svc.set_plan_active(plan_id, is_active)
    await db.commit()
    item = PlanPublic.model_validate(plan)
    item.subscriber_count = await svc.plan_subscriber_count(plan.id)
    return item


@router.get("/payments", response_model=PaymentListResponse)
async def list_payments(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str = "",
    status: str = "all",
    limit: int = 50,
    offset: int = 0,
):
    del admin
    return await PlatformBillingService(db).list_payments(
        search=search, status=status, limit=limit, offset=offset
    )


@router.post("/payments/manual")
async def create_manual_payment(
    data: ManualPaymentCreate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    payment = await PlatformBillingService(db).create_manual_payment(
        data.model_dump(), admin_id=admin.id
    )
    await db.commit()
    return {"id": payment.id, "status": payment.status, "subscription_id": payment.subscription_id}


@router.get("/payments/pending-count")
async def pending_payment_count(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    count = await PlatformBillingService(db).pending_payment_count()
    return {"count": count}


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(
    payment_id: int,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    payment = await PlatformBillingService(db).confirm_payment(payment_id, admin.id)
    await db.commit()
    return {"id": payment.id, "status": payment.status, "subscription_id": payment.subscription_id}


@router.post("/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: int,
    data: PaymentRejectRequest,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    payment = await PlatformBillingService(db).reject_payment(payment_id, admin.id, data.reason)
    await db.commit()
    return {"id": payment.id, "status": payment.status, "rejection_reason": payment.rejection_reason}


@router.get("/billing/payment-settings", response_model=PaymentSettingsPublic)
async def get_payment_settings(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    data = await PlatformBillingService(db).get_payment_settings()
    return PaymentSettingsPublic(**data)


@router.patch("/billing/payment-settings", response_model=PaymentSettingsPublic)
async def update_payment_settings(
    data: PaymentSettingsUpdate,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del admin
    updated = await PlatformBillingService(db).update_payment_settings(data.model_dump(exclude_unset=True))
    await db.commit()
    return PaymentSettingsPublic(**updated)


@router.post("/billing/payment-settings/qris-upload")
async def upload_qris_image(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    del admin
    content = await file.read()
    url = await PlatformBillingService(db).save_qris_image(
        content, file.content_type, file.filename or "qris.png"
    )
    await db.commit()
    return {"qris_image_url": get_upload_url(url)}


@router.get("/trials", response_model=TrialListResponse)
async def list_trials(
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
):
    del admin
    return await PlatformBillingService(db).list_trials(limit=limit, offset=offset)


@router.patch("/trials/{subscription_id}/extend")
async def extend_trial(
    subscription_id: int,
    data: TrialExtendRequest,
    admin: Annotated[PlatformAdmin, Depends(get_current_platform_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sub = await PlatformBillingService(db).extend_trial(
        admin.id, subscription_id, data.extra_days, data.reason
    )
    await db.commit()
    return {"subscription_id": sub.id, "trial_ends_at": sub.trial_ends_at}
