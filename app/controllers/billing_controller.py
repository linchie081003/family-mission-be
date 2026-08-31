"""Parent-facing billing: plans, subscription, upgrade requests."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_parent
from app.core.database import get_db
from app.models.models import Parent
from app.schemas import (
    BillingPlanPublic,
    BillingSubscriptionPublic,
    PaymentSettingsPublic,
    PendingPaymentPublic,
    UpgradeRequestCreate,
    UpgradeRequestResponse,
)
from app.services.platform_billing_service import PlatformBillingService
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[BillingPlanPublic])
async def list_billing_plans(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del parent
    plans = await PlatformBillingService(db).list_public_plans()
    return [BillingPlanPublic.model_validate(p) for p in plans]


@router.get("/subscription", response_model=BillingSubscriptionPublic)
async def get_billing_subscription(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    status = await SubscriptionService(db).get_subscription_status(parent.family_id)
    return BillingSubscriptionPublic(**status)


@router.get("/payment-instructions", response_model=PaymentSettingsPublic)
async def get_payment_instructions(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del parent
    data = await PlatformBillingService(db).get_payment_settings()
    return PaymentSettingsPublic(**data)


@router.post("/upgrade-request", response_model=UpgradeRequestResponse)
async def create_upgrade_request(
    data: UpgradeRequestCreate,
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await PlatformBillingService(db).create_upgrade_request(
        parent.family_id,
        plan_slug=data.plan_slug,
        method=data.method,
        proof_image=data.proof_image,
        provider_ref=data.provider_ref,
        note=data.note,
    )
    await db.commit()
    return UpgradeRequestResponse(
        payment_id=result["payment_id"],
        amount=result["amount"],
        currency=result["currency"],
        plan_slug=result["plan_slug"],
        plan_name=result["plan_name"],
        method=result["method"],
        instructions=PaymentSettingsPublic(**result["instructions"]),
    )


@router.get("/pending-payment", response_model=PendingPaymentPublic | None)
async def get_pending_payment(
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pending = await PlatformBillingService(db).get_pending_payment_for_family(parent.family_id)
    if not pending:
        return None
    return PendingPaymentPublic(**pending)
