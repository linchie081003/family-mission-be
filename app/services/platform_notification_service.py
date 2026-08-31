from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Family, NotificationType, Parent, Payment, Plan, PlatformAdmin, PlatformBroadcast, PlatformAuditLog, PlatformNotification
from app.services.email_service import send_email
from app.services.notification_service import notify_parent
from app.core.config import settings


class PlatformNotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify_family_registration(self, family: Family) -> PlatformNotification:
        notif = PlatformNotification(
            type="family_registration",
            title="Pendaftaran keluarga baru",
            body=f"{family.family_name} ({family.email}) menunggu persetujuan.",
            family_id=family.id,
            data={
                "family_name": family.family_name,
                "email": family.email,
                "family_code": family.family_code,
            },
        )
        self.db.add(notif)
        await self.db.flush()

        admin = await self.db.scalar(select(PlatformAdmin).order_by(PlatformAdmin.id).limit(1))
        if admin:
            recipient = admin.notification_email or admin.email
            await send_email(
                to=recipient,
                subject=f"[Family Mission] Pendaftaran baru: {family.family_name}",
                body=(
                    f"Keluarga baru mendaftar dan menunggu persetujuan.\n\n"
                    f"Nama: {family.family_name}\n"
                    f"Email: {family.email}\n"
                    f"Kode: {family.family_code}\n\n"
                    f"Login Super Admin untuk menyetujui tenant."
                ),
            )
        return notif

    async def notify_payment_proof_uploaded(
        self,
        family: Family,
        payment: Payment,
        plan: Plan,
    ) -> PlatformNotification:
        amount_fmt = f"Rp{payment.amount:,}".replace(",", ".")
        notif = PlatformNotification(
            type="payment_proof_uploaded",
            title="Bukti pembayaran baru",
            body=f"{family.family_name} mengupload bukti upgrade ke {plan.name} — {amount_fmt}",
            family_id=family.id,
            data={
                "payment_id": payment.id,
                "plan_slug": plan.slug,
                "amount": payment.amount,
                "proof_image_url": payment.proof_image_url,
                "action_path": "/admin/billing/verification",
            },
        )
        self.db.add(notif)
        await self.db.flush()

        admin = await self.db.scalar(select(PlatformAdmin).order_by(PlatformAdmin.id).limit(1))
        if admin:
            recipient = admin.notification_email or admin.email
            verify_url = f"{settings.frontend_base_url}/admin/billing/verification?payment_id={payment.id}"
            await send_email(
                to=recipient,
                subject=f"[Family Mission] Bukti pembayaran: {family.family_name}",
                body=(
                    f"Keluarga mengupload bukti pembayaran upgrade.\n\n"
                    f"Nama: {family.family_name}\n"
                    f"Email: {family.email}\n"
                    f"Paket: {plan.name}\n"
                    f"Jumlah: {amount_fmt}\n"
                    f"Metode: {payment.provider}\n\n"
                    f"Verifikasi di: {verify_url}"
                ),
            )
        return notif

    async def list_notifications(self, *, limit: int = 50, unread_only: bool = False) -> list[PlatformNotification]:
        q = select(PlatformNotification).order_by(PlatformNotification.created_at.desc()).limit(min(limit, 200))
        if unread_only:
            q = q.where(PlatformNotification.is_read.is_(False))
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def unread_count(self) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(PlatformNotification).where(PlatformNotification.is_read.is_(False))
        ) or 0

    async def mark_read(self, notification_id: int) -> PlatformNotification | None:
        notif = await self.db.get(PlatformNotification, notification_id)
        if not notif:
            return None
        notif.is_read = True
        await self.db.flush()
        return notif

    async def mark_all_read(self) -> int:
        result = await self.db.execute(
            update(PlatformNotification).where(PlatformNotification.is_read.is_(False)).values(is_read=True)
        )
        return result.rowcount or 0

    async def broadcast_to_families(
        self,
        admin: PlatformAdmin,
        *,
        title: str,
        body: str,
        also_send_email: bool = False,
    ) -> PlatformBroadcast:
        result = await self.db.execute(select(Family).where(Family.is_active.is_(True)))
        families = list(result.scalars().all())
        reached = 0
        for family in families:
            await notify_parent(
                self.db,
                family.id,
                NotificationType.SYSTEM,
                title,
                body,
                data={"source": "platform_broadcast"},
            )
            reached += 1
            if also_send_email:
                parent = await self.db.scalar(
                    select(Parent).where(Parent.family_id == family.id, Parent.is_primary.is_(True))
                )
                if parent:
                    await send_email(
                        to=parent.email,
                        subject=f"[Family Mission] {title}",
                        body=body,
                    )

        record = PlatformBroadcast(
            platform_admin_id=admin.id,
            title=title,
            body=body,
            target="all_active",
            families_reached=reached,
            send_email=also_send_email,
        )
        self.db.add(record)
        if families:
            entry = PlatformAuditLog(
                platform_admin_id=admin.id,
                family_id=families[0].id,
                feature_key="broadcast",
                enabled=True,
                summary=f"Super Admin broadcast ke {reached} keluarga: {title}",
                details={"title": title, "families_reached": reached, "send_email": also_send_email},
            )
            self.db.add(entry)
        await self.db.flush()
        return record

    async def list_broadcasts(self, limit: int = 20) -> list[PlatformBroadcast]:
        result = await self.db.execute(
            select(PlatformBroadcast)
            .order_by(PlatformBroadcast.created_at.desc())
            .limit(min(max(limit, 1), 100))
        )
        return list(result.scalars().all())
