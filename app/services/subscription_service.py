from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tokens import utcnow
from app.models.models import Family, Payment, Plan, Subscription
from app.services.plan_presets import apply_plan_features


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_plan_by_slug(self, slug: str) -> Plan:
        plan = await self.db.scalar(select(Plan).where(Plan.slug == slug, Plan.is_active.is_(True)))
        if not plan:
            raise HTTPException(status_code=404, detail=f"Paket '{slug}' tidak ditemukan")
        return plan

    async def get_subscription(self, family_id: int) -> Subscription | None:
        return await self.db.scalar(select(Subscription).where(Subscription.family_id == family_id))

    async def _get_pending_payment(self, family_id: int) -> Payment | None:
        return await self.db.scalar(
            select(Payment)
            .where(Payment.family_id == family_id, Payment.status == "pending")
            .order_by(Payment.created_at.desc())
            .limit(1)
        )

    async def start_trial(
        self,
        family: Family,
        *,
        plan_slug: str = "family",
        days: int = 10,
    ) -> Subscription:
        plan = await self.get_plan_by_slug(plan_slug)
        now = utcnow()
        sub = await self.get_subscription(family.id)
        if sub:
            sub.plan_id = plan.id
            sub.status = "trial"
            sub.is_demo = False
            sub.trial_ends_at = now + timedelta(days=days)
            sub.current_period_start = None
            sub.current_period_end = None
            sub.updated_at = now
        else:
            sub = Subscription(
                family_id=family.id,
                plan_id=plan.id,
                status="trial",
                trial_ends_at=now + timedelta(days=days),
                is_demo=False,
            )
            self.db.add(sub)

        apply_plan_features(family, plan)
        family.activated_at = now
        family.is_active = True
        family.activation_preset = plan_slug
        await self.db.flush()
        return sub

    async def activate_from_payment(
        self,
        family: Family,
        plan: Plan,
        *,
        period_days: int = 30,
    ) -> Subscription:
        now = utcnow()
        sub = await self.get_subscription(family.id)
        if sub:
            sub.plan_id = plan.id
            sub.status = "active"
            sub.is_demo = False
            sub.trial_ends_at = None
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=period_days)
            sub.updated_at = now
        else:
            sub = Subscription(
                family_id=family.id,
                plan_id=plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=period_days),
                is_demo=False,
            )
            self.db.add(sub)

        apply_plan_features(family, plan)
        family.activated_at = family.activated_at or now
        family.activation_preset = plan.slug
        family.is_active = True
        await self.db.flush()
        return sub

    async def assign_demo_plan(
        self,
        family: Family,
        plan_slug: str,
        *,
        note: str | None = None,
    ) -> Subscription:
        plan = await self.get_plan_by_slug(plan_slug)
        now = utcnow()
        sub = await self.get_subscription(family.id)
        if sub:
            sub.plan_id = plan.id
            sub.status = "active"
            sub.is_demo = True
            sub.trial_ends_at = None
            sub.current_period_start = now
            sub.current_period_end = None
            sub.manual_notes = note or sub.manual_notes
            sub.updated_at = now
        else:
            sub = Subscription(
                family_id=family.id,
                plan_id=plan.id,
                status="active",
                is_demo=True,
                current_period_start=now,
                manual_notes=note,
            )
            self.db.add(sub)

        apply_plan_features(family, plan)
        family.activated_at = family.activated_at or now
        family.activation_preset = plan_slug
        family.is_active = True
        await self.db.flush()
        return sub

    async def revoke_demo(self, family: Family) -> Subscription:
        sub = await self.get_subscription(family.id)
        if not sub or not sub.is_demo:
            raise HTTPException(status_code=400, detail="Keluarga ini bukan akun demo")
        sub.is_demo = False
        await self.db.flush()
        return await self.downgrade_to_basic(family)

    async def downgrade_to_basic(self, family: Family) -> Subscription:
        plan = await self.get_plan_by_slug("basic")
        now = utcnow()
        sub = await self.get_subscription(family.id)
        if sub:
            sub.plan_id = plan.id
            sub.status = "active"
            sub.is_demo = False
            sub.trial_ends_at = None
            sub.current_period_start = now
            sub.current_period_end = None
            sub.updated_at = now
        else:
            sub = Subscription(
                family_id=family.id,
                plan_id=plan.id,
                status="active",
                current_period_start=now,
                is_demo=False,
            )
            self.db.add(sub)

        apply_plan_features(family, plan)
        family.activation_preset = "basic"
        await self.db.flush()
        return sub

    async def check_and_expire_trials(self, family_id: int) -> bool:
        """Return True if trial was expired and downgraded."""
        sub = await self.get_subscription(family_id)
        if not sub or sub.is_demo:
            return False
        if sub.status != "trial" or not sub.trial_ends_at:
            return False
        if sub.trial_ends_at > utcnow():
            return False
        family = await self.db.get(Family, family_id)
        if not family:
            return False
        await self.downgrade_to_basic(family)
        return True

    async def get_subscription_status(self, family_id: int) -> dict:
        await self.check_and_expire_trials(family_id)
        sub = await self.get_subscription(family_id)
        pending = await self._get_pending_payment(family_id)
        pending_payment = None
        if pending:
            meta = pending.payment_metadata or {}
            plan_slug = meta.get("plan_slug") if isinstance(meta, dict) else None
            pending_payment = {
                "payment_id": pending.id,
                "plan_slug": plan_slug,
                "amount": pending.amount,
                "created_at": pending.created_at,
                "has_proof": bool(pending.proof_image_url),
            }

        if not sub:
            return {
                "has_subscription": False,
                "status": None,
                "plan_slug": "basic",
                "plan_name": "Basic",
                "trial_ends_at": None,
                "days_remaining": None,
                "current_period_end": None,
                "can_upgrade": True,
                "is_demo": False,
                "pending_payment": pending_payment,
            }

        plan = await self.db.get(Plan, sub.plan_id)
        now = utcnow()
        days_remaining = None
        if sub.status == "trial" and sub.trial_ends_at:
            days_remaining = max(0, (sub.trial_ends_at.date() - now.date()).days)

        plan_slug = plan.slug if plan else "basic"
        tier_order = {"basic": 0, "standard": 1, "family": 2}

        return {
            "has_subscription": True,
            "status": sub.status,
            "plan_slug": plan_slug,
            "plan_name": plan.name if plan else "Basic",
            "trial_ends_at": sub.trial_ends_at,
            "days_remaining": days_remaining,
            "current_period_end": sub.current_period_end,
            "can_upgrade": tier_order.get(plan_slug, 0) < 2 and not sub.is_demo,
            "is_demo": bool(sub.is_demo),
            "pending_payment": pending_payment,
        }
