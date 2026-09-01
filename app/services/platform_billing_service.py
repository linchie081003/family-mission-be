from datetime import timedelta
import base64
import os
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tokens import utcnow
from app.core.upload_url import get_upload_url
from app.models.models import Family, Payment, Plan, PlatformAuditLog, PlatformPaymentSettings, Subscription
from app.services.proof_image import validate_proof_image
from app.services.subscription_service import SubscriptionService


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
            if sub.is_demo:
                slug = plan.slug
                if slug not in tier_breakdown:
                    tier_breakdown[slug] = {"plan_name": plan.name, "count": 0, "mrr": 0}
                tier_breakdown[slug]["count"] += 1
                continue
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
        result = await self.db.execute(
            select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.id)
        )
        return list(result.scalars().all())

    async def list_public_plans(self) -> list[Plan]:
        return await self.list_plans()

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
        if "feature_preset" in data and data["feature_preset"] is not None:
            allowed = {
                "rewards_enabled",
                "mission_evidence_enabled",
                "quiz_enabled",
                "chat_enabled",
                "agenda_enabled",
                "daily_mission_limit",
            }
            preset = data["feature_preset"]
            if not isinstance(preset, dict) or any(k not in allowed for k in preset):
                raise HTTPException(status_code=400, detail="feature_preset tidak valid")
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

    async def _get_payment_settings_row(self) -> PlatformPaymentSettings:
        row = await self.db.get(PlatformPaymentSettings, 1)
        if not row:
            row = PlatformPaymentSettings(
                id=1,
                payment_methods_enabled={"qris_static": True, "bank_transfer": True},
            )
            self.db.add(row)
            await self.db.flush()
        return row

    def _settings_to_dict(self, row: PlatformPaymentSettings) -> dict:
        enabled = row.payment_methods_enabled or {"qris_static": True, "bank_transfer": True}
        return {
            "qris_image_url": get_upload_url(row.qris_image_url or settings.payment_qris_image_url or None),
            "qris_merchant_name": row.qris_merchant_name or None,
            "bank_name": row.bank_name or settings.payment_bank_name or None,
            "bank_account_number": row.bank_account_number or settings.payment_bank_account or None,
            "bank_account_holder": row.bank_account_holder or settings.payment_bank_holder or None,
            "transfer_instructions": row.transfer_instructions or settings.payment_instructions_text or None,
            "payment_methods_enabled": enabled,
            "updated_at": row.updated_at,
        }

    async def get_payment_settings(self) -> dict:
        row = await self._get_payment_settings_row()
        return self._settings_to_dict(row)

    async def update_payment_settings(self, data: dict) -> dict:
        row = await self._get_payment_settings_row()
        for key in (
            "qris_image_url",
            "qris_merchant_name",
            "bank_name",
            "bank_account_number",
            "bank_account_holder",
            "transfer_instructions",
            "payment_methods_enabled",
        ):
            if key in data and data[key] is not None:
                setattr(row, key, data[key])
        row.updated_at = utcnow()
        await self.db.flush()
        return self._settings_to_dict(row)

    async def save_qris_image(self, content: bytes, content_type: str | None, filename: str) -> str:
        from app.core.security import validate_upload

        validate_upload(filename, content_type, len(content))
        os.makedirs(settings.upload_dir, exist_ok=True)
        ext = os.path.splitext(filename)[1].lower() or ".png"
        safe_name = f"qris_{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(settings.upload_dir, safe_name)
        with open(filepath, "wb") as f:
            f.write(content)
        url = f"/uploads/{safe_name}"
        await self.update_payment_settings({"qris_image_url": url})
        return get_upload_url(url)

    def _save_proof_image_file(self, proof_image: str) -> str:
        cleaned = validate_proof_image(proof_image, required=True)
        if cleaned and cleaned.startswith("/uploads/"):
            return cleaned

        assert cleaned is not None
        match = re.match(r"data:image/(\w+);base64,(.+)", cleaned, re.DOTALL)
        if not match:
            raise HTTPException(status_code=400, detail="Format foto bukti tidak valid")
        ext = ".jpg" if match.group(1) in ("jpeg", "jpg") else f".{match.group(1)}"
        if ext == ".jpeg":
            ext = ".jpg"
        content = base64.b64decode(match.group(2))
        os.makedirs(settings.upload_dir, exist_ok=True)
        safe_name = f"payment_proof_{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(settings.upload_dir, safe_name)
        with open(filepath, "wb") as f:
            f.write(content)
        return f"/uploads/{safe_name}"

    def _payment_to_dict(self, payment: Payment, family: Family) -> dict:
        plan_slug = None
        meta = payment.payment_metadata or {}
        if isinstance(meta, dict):
            plan_slug = meta.get("plan_slug")
        return {
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
            "plan_slug": plan_slug,
            "subscription_id": payment.subscription_id,
            "proof_image_url": get_upload_url(payment.proof_image_url),
            "rejection_reason": payment.rejection_reason,
        }

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
            items.append(self._payment_to_dict(payment, family))
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def pending_payment_count(self) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == "pending")
        ) or 0

    async def get_pending_payment_for_family(self, family_id: int) -> dict | None:
        payment = await self.db.scalar(
            select(Payment)
            .where(Payment.family_id == family_id, Payment.status == "pending")
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        if not payment:
            return None
        meta = payment.payment_metadata or {}
        plan_slug = meta.get("plan_slug") if isinstance(meta, dict) else None
        plan_name = None
        if plan_slug:
            plan = await self.db.scalar(select(Plan).where(Plan.slug == plan_slug))
            plan_name = plan.name if plan else None
        return {
            "payment_id": payment.id,
            "plan_slug": plan_slug,
            "plan_name": plan_name,
            "amount": payment.amount,
            "status": payment.status,
            "created_at": payment.created_at,
            "has_proof": bool(payment.proof_image_url),
            "rejection_reason": payment.rejection_reason,
        }

    async def create_manual_payment(self, data: dict, *, admin_id: int | None = None) -> Payment:
        pending_payment_id = data.get("pending_payment_id")
        if pending_payment_id and admin_id:
            return await self.confirm_payment(pending_payment_id, admin_id)

        family = await self.db.get(Family, data["family_id"])
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        plan_id = data.get("plan_id")
        billing_period = data.get("billing_period", "monthly")
        period_days = 365 if billing_period == "yearly" else 30

        plan = None
        if plan_id:
            plan = await self.get_plan(plan_id)

        if not plan:
            raise HTTPException(status_code=400, detail="plan_id wajib untuk aktivasi subscription")

        now = utcnow()
        payment = Payment(
            family_id=data["family_id"],
            amount=data["amount"],
            currency=data.get("currency", "IDR"),
            status="paid",
            provider=data.get("provider", "manual"),
            provider_ref=data.get("provider_ref"),
            invoice_number=data.get("invoice_number"),
            description=data.get("description"),
            paid_at=now,
            verified_at=now,
            verified_by_admin_id=admin_id,
            payment_metadata={"plan_slug": plan.slug, "billing_period": billing_period},
        )
        self.db.add(payment)
        await self.db.flush()

        sub = await SubscriptionService(self.db).activate_from_payment(family, plan, period_days=period_days)
        payment.subscription_id = sub.id

        if admin_id:
            entry = PlatformAuditLog(
                platform_admin_id=admin_id,
                family_id=family.id,
                feature_key="payment_activate_subscription",
                enabled=True,
                summary=f"Pembayaran manual mengaktifkan paket {plan.name} untuk {family.family_name}",
                details={
                    "payment_id": payment.id,
                    "plan_slug": plan.slug,
                    "amount": payment.amount,
                    "billing_period": billing_period,
                },
            )
            self.db.add(entry)

        await self.db.flush()
        return payment

    async def confirm_payment(self, payment_id: int, admin_id: int) -> Payment:
        payment = await self.db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Pembayaran tidak ditemukan")
        if payment.status != "pending":
            raise HTTPException(status_code=400, detail="Hanya pembayaran pending yang bisa dikonfirmasi")

        family = await self.db.get(Family, payment.family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        meta = payment.payment_metadata or {}
        plan_slug = meta.get("plan_slug") if isinstance(meta, dict) else None
        billing_period = meta.get("billing_period", "monthly") if isinstance(meta, dict) else "monthly"
        if not plan_slug:
            raise HTTPException(status_code=400, detail="Metadata plan_slug tidak ditemukan")

        plan = await self.db.scalar(select(Plan).where(Plan.slug == plan_slug))
        if not plan:
            raise HTTPException(status_code=404, detail="Paket tidak ditemukan")

        period_days = 365 if billing_period == "yearly" else 30
        now = utcnow()
        sub = await SubscriptionService(self.db).activate_from_payment(family, plan, period_days=period_days)

        payment.status = "paid"
        payment.paid_at = now
        payment.verified_at = now
        payment.verified_by_admin_id = admin_id
        payment.subscription_id = sub.id

        entry = PlatformAuditLog(
            platform_admin_id=admin_id,
            family_id=family.id,
            feature_key="payment_confirm",
            enabled=True,
            summary=f"Pembayaran dikonfirmasi — paket {plan.name} untuk {family.family_name}",
            details={
                "payment_id": payment.id,
                "plan_slug": plan.slug,
                "amount": payment.amount,
            },
        )
        self.db.add(entry)
        await self.db.flush()
        return payment

    async def reject_payment(self, payment_id: int, admin_id: int, reason: str) -> Payment:
        payment = await self.db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Pembayaran tidak ditemukan")
        if payment.status != "pending":
            raise HTTPException(status_code=400, detail="Hanya pembayaran pending yang bisa ditolak")

        family = await self.db.get(Family, payment.family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Keluarga tidak ditemukan")

        now = utcnow()
        payment.status = "failed"
        payment.rejection_reason = reason
        payment.verified_at = now
        payment.verified_by_admin_id = admin_id

        entry = PlatformAuditLog(
            platform_admin_id=admin_id,
            family_id=family.id,
            feature_key="payment_reject",
            enabled=False,
            summary=f"Pembayaran ditolak untuk {family.family_name}",
            details={"payment_id": payment.id, "reason": reason},
        )
        self.db.add(entry)
        await self.db.flush()
        return payment

    async def create_upgrade_request(
        self,
        family_id: int,
        *,
        plan_slug: str,
        method: str,
        proof_image: str,
        provider_ref: str | None = None,
        note: str | None = None,
    ) -> dict:
        existing_pending = await self.db.scalar(
            select(func.count()).select_from(Payment).where(
                Payment.family_id == family_id,
                Payment.status == "pending",
            )
        )
        if existing_pending:
            raise HTTPException(
                status_code=400,
                detail="Masih ada pembayaran yang menunggu verifikasi. Tunggu konfirmasi admin.",
            )

        plan = await self.db.scalar(select(Plan).where(Plan.slug == plan_slug, Plan.is_active.is_(True)))
        if not plan:
            raise HTTPException(status_code=404, detail="Paket tidak ditemukan")
        if plan.slug == "basic":
            raise HTTPException(status_code=400, detail="Tidak bisa upgrade ke Basic")

        instructions = await self.get_payment_settings()
        enabled = instructions.get("payment_methods_enabled") or {}
        if method == "qris_static" and not enabled.get("qris_static", True):
            raise HTTPException(status_code=400, detail="Metode QRIS tidak aktif")
        if method == "bank_transfer" and not enabled.get("bank_transfer", True):
            raise HTTPException(status_code=400, detail="Metode transfer bank tidak aktif")

        if method == "qris_static" and not instructions.get("qris_image_url"):
            raise HTTPException(status_code=503, detail="QRIS belum dikonfigurasi oleh admin")
        if method == "bank_transfer" and not instructions.get("bank_account_number"):
            raise HTTPException(status_code=503, detail="Rekening transfer belum dikonfigurasi oleh admin")

        proof_url = self._save_proof_image_file(proof_image)

        payment = Payment(
            family_id=family_id,
            amount=plan.price_monthly,
            currency=plan.currency,
            status="pending",
            provider=method,
            provider_ref=provider_ref,
            description=note or f"Upgrade ke {plan.name}",
            proof_image_url=proof_url,
            payment_metadata={"plan_slug": plan.slug, "billing_period": "monthly"},
        )
        self.db.add(payment)
        await self.db.flush()

        family = await self.db.get(Family, family_id)
        if family:
            from app.services.platform_notification_service import PlatformNotificationService

            await PlatformNotificationService(self.db).notify_payment_proof_uploaded(
                family, payment, plan
            )

        return {
            "payment_id": payment.id,
            "amount": payment.amount,
            "currency": payment.currency,
            "plan_slug": plan.slug,
            "plan_name": plan.name,
            "method": method,
            "instructions": instructions,
        }

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
