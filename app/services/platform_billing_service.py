from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tokens import utcnow
from app.models.models import Family, Payment, Plan, PlatformAuditLog, Subscription
from app.services.plan_presets import apply_plan_features


class PlatformBillingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def billing_stats(self) -> dict:
        now = utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

        active_subs = await self.db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.status.in_(["active", "trial"]))
        )
        rows = active_subs.all()
        mrr = 0
        tier_breakdown: dict[str, dict] = {}
        trial_count = 0
        for sub, plan in rows:
            if sub.status == "trial":
                trial_count += 1
            monthly = plan.price_monthly or 0
            if sub.status == "active":
                mrr += monthly
            slug = plan.slug
            if slug not in tier_breakdown:
                tier_breakdown[slug] = {"plan_name": plan.name, "count": 0, "mrr": 0}
            tier_breakdown[slug]["count"] += 1
            if sub.status == "active":
                tier_breakdown[slug]["mrr"] += monthly

        revenue_this_month = await self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == "paid",
                Payment.paid_at >= month_start,
            )
        ) or 0
        revenue_last_month = await self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == "paid",
                Payment.paid_at >= prev_month_start,
                Payment.paid_at < month_start,
            )
        ) or 0

        trials_started = await self.db.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.created_at >= month_start - timedelta(days=30)
            )
        ) or 0
        trials_converted = await self.db.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.status == "active",
                Subscription.updated_at >= month_start - timedelta(days=30),
            )
        ) or 0
        conversion_rate = round((trials_converted / trials_started * 100), 1) if trials_started else 0.0

        return {
            "mrr": mrr,
            "revenue_this_month": revenue_this_month,
            "revenue_last_month": revenue_last_month,
            "trial_active_count": trial_count,
            "trial_conversion_rate": conversion_rate,
            "tier_breakdown": list(tier_breakdown.values()),
        }

    async def list_plans(self) -> list[Plan]:
        result = await self.db.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
        return list(result.scalars().all())

    async def get_plan(self, plan_id: int) -> Plan:
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Paket tidak ditemukan")
        return plan

    async def create_plan(self, data: dict) -> Plan:
        existing = await self.db.scalar(select(Plan).where(Plan.slug == data["slug"]))
        if existing:
            raise HTTPException(status_code=400, detail="Slug paket sudah digunakan")
        plan = Plan(**data)
        self.db.add(plan)
        await self.db.flush()
        return plan

    async def update_plan(self, plan_id: int, data: dict) -> Plan:
        plan = await self.get_plan(plan_id)
        for key, val in data.items():
            if val is not None and hasattr(plan, key):
                setattr(plan, key, val)
        plan.updated_at = utcnow()
        await self.db.flush()
        return plan

    async def set_plan_active(self, plan_id: int, is_active: bool) -> Plan:
        plan = await self.get_plan(plan_id)
        plan.is_active = is_active
        await self.db.flush()
        return plan

    async def list_payments(
        self,
        *,
        search: str = "",
        status: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        q = select(Payment, Family).join(Family, Family.id == Payment.family_id)
        count_q = select(func.count()).select_from(Payment)

        if search.strip():
            term = f"%{search.strip()}%"
            filt = or_(
                Family.family_name.ilike(term),
                Family.email.ilike(term),
                Payment.invoice_number.ilike(term),
                Payment.provider_ref.ilike(term),
            )
            q = q.where(filt)
            count_q = count_q.join(Family, Family.id == Payment.family_id).where(filt)

        if status != "all":
            q = q.where(Payment.status == status)
            count_q = count_q.where(Payment.status == status)

        total = await self.db.scalar(count_q) or 0
        q = q.order_by(Payment.created_at.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0))
        result = await self.db.execute(q)
        items = []
        for payment, family in result.all():
            items.append({
                "id": payment.id,
                "family_id": family.id,
                "family_name": family.family_name,
                "email": family.email,
                "amount": payment.amount,
                "currency": payment.currency,
                "status": payment.status,
                "provider": payment.provider,
                "provider_ref": payment.provider_ref,
                "invoice_number": payment.invoice_number,
                "description": payment.description,
                "paid_at": payment.paid_at,
                "created_at": payment.created_at,
            })
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def create_manual_payment(self, data: dict) -> Payment:
        family = await self.db.get(Family, data["family_id"])
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")
        payment = Payment(
            family_id=data["family_id"],
            subscription_id=data.get("subscription_id"),
            amount=data["amount"],
            currency=data.get("currency", "IDR"),
            status="paid",
            provider="manual",
            provider_ref=data.get("provider_ref"),
            invoice_number=data.get("invoice_number"),
            description=data.get("description"),
            paid_at=utcnow(),
        )
        self.db.add(payment)
        await self.db.flush()
        return payment

    async def list_trials(self, *, limit: int = 50, offset: int = 0) -> dict:
        now = utcnow()
        q = (
            select(Subscription, Family, Plan)
            .join(Family, Family.id == Subscription.family_id)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.status == "trial")
            .order_by(Subscription.trial_ends_at.asc().nulls_last())
            .limit(min(max(limit, 1), 200))
            .offset(max(offset, 0))
        )
        count_q = select(func.count()).select_from(Subscription).where(Subscription.status == "trial")
        total = await self.db.scalar(count_q) or 0
        result = await self.db.execute(q)
        items = []
        for sub, family, plan in result.all():
            days_remaining = None
            if sub.trial_ends_at:
                days_remaining = max(0, (sub.trial_ends_at.date() - now.date()).days)
            items.append({
                "subscription_id": sub.id,
                "family_id": family.id,
                "family_name": family.family_name,
                "email": family.email,
                "plan_name": plan.name,
                "plan_slug": plan.slug,
                "trial_ends_at": sub.trial_ends_at,
                "days_remaining": days_remaining,
                "referral_code": family.referral_code,
                "manual_notes": sub.manual_notes,
            })
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def extend_trial(
        self,
        admin_id: int,
        subscription_id: int,
        extra_days: int,
        reason: str,
    ) -> Subscription:
        sub = await self.db.get(Subscription, subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription tidak ditemukan")
        if sub.status != "trial":
            raise HTTPException(status_code=400, detail="Hanya trial yang bisa diperpanjang")
        now = utcnow()
        base = sub.trial_ends_at if sub.trial_ends_at and sub.trial_ends_at > now else now
        sub.trial_ends_at = base + timedelta(days=extra_days)
        note = f"[{now.date()}] +{extra_days}d: {reason}"
        sub.manual_notes = f"{sub.manual_notes or ''}\n{note}".strip()
        sub.updated_at = now

        family = await self.db.get(Family, sub.family_id)
        if family:
            entry = PlatformAuditLog(
                platform_admin_id=admin_id,
                family_id=family.id,
                feature_key="trial_extend",
                enabled=True,
                summary=f"Super Admin memperpanjang trial {extra_days} hari untuk {family.family_name}",
                details={"extra_days": extra_days, "reason": reason, "trial_ends_at": sub.trial_ends_at.isoformat()},
            )
            self.db.add(entry)
        await self.db.flush()
        return sub

    async def plan_subscriber_count(self, plan_id: int) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.plan_id == plan_id,
                Subscription.status.in_(["active", "trial"]),
            )
        ) or 0
