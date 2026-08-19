from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Family, PlatformAdmin, PlatformNotification
from app.services.email_service import send_email


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
