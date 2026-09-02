import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.core.config import settings
from app.core.tokens import generate_raw_token, hash_token, utcnow
from app.models.models import Family, Parent, ParentInvite, ParentRole
from app.repositories.parent_repository import ParentRepository
from app.schemas import AcceptParentInviteRequest, ParentInviteCreate, ParentPublic
from app.services.email_service import send_coparent_invite_email
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ParentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.parents = ParentRepository(db)

    async def list_parents(self, parent: Parent) -> list[ParentPublic]:
        members = await self.parents.list_by_family(parent.family_id)
        return [ParentPublic.model_validate(m) for m in members]

    async def invite(self, current: Parent, data: ParentInviteCreate) -> dict:
        if await self.parents.email_exists(data.email):
            raise HTTPException(status_code=400, detail="Email sudah terdaftar")
        if await self.parents.count_by_role(current.family_id, data.role) >= 1:
            raise HTTPException(status_code=400, detail=f"Peran {data.role.value} sudah terisi di keluarga ini")

        members = await self.parents.list_by_family(current.family_id)
        if len(members) >= 2:
            raise HTTPException(status_code=400, detail="Maksimal 2 orang tua per keluarga")

        raw = generate_raw_token()
        invite = ParentInvite(
            family_id=current.family_id,
            invited_by_parent_id=current.id,
            email=data.email,
            name=data.name,
            role=data.role,
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(hours=72),
        )
        self.db.add(invite)
        await self.db.flush()

        fam = await self.db.get(Family, current.family_id)
        link = f"{settings.frontend_base_url}/accept-invite?token={raw}"
        sent = await send_coparent_invite_email(
            to=data.email,
            inviter_name=current.name,
            family_name=fam.family_name if fam else "Keluarga",
            link=link,
        )
        if not sent:
            logger.info("DEV co-parent invite for %s: %s", data.email, link)
        await self.db.commit()
        if sent:
            return {"message": f"Undangan dikirim ke {data.email}", "email_sent": True}
        return {
            "message": (
                f"Undangan tersimpan untuk {data.email}, tetapi email belum terkirim. "
                "Pastikan BREVO_API_KEY dan BREVO_SENDER_EMAIL sudah diset di server."
            ),
            "email_sent": False,
        }

    async def accept_invite(self, data: AcceptParentInviteRequest) -> dict:
        result = await self.db.execute(
            select(ParentInvite).where(
                ParentInvite.token_hash == hash_token(data.token),
                ParentInvite.accepted_at.is_(None),
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise HTTPException(status_code=400, detail="Undangan tidak valid atau kedaluwarsa")
        exp = invite.expires_at
        if exp.tzinfo is None:
            from datetime import timezone
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < utcnow():
            raise HTTPException(status_code=400, detail="Undangan tidak valid atau kedaluwarsa")
        if await self.parents.email_exists(invite.email):
            raise HTTPException(status_code=400, detail="Email sudah terdaftar")

        parent = await self.parents.create(
            family_id=invite.family_id,
            email=invite.email,
            password=data.password,
            name=invite.name,
            role=invite.role,
            is_primary=False,
            email_verified=True,
        )
        invite.accepted_at = utcnow()
        await self.db.commit()
        return {"message": "Undangan diterima. Silakan login.", "parent_id": parent.id}

    async def list_pending_invites(self, current: Parent) -> list[dict]:
        result = await self.db.execute(
            select(ParentInvite)
            .where(
                ParentInvite.family_id == current.family_id,
                ParentInvite.accepted_at.is_(None),
            )
            .order_by(ParentInvite.created_at.desc())
        )
        now = utcnow()
        invites = []
        for invite in result.scalars().all():
            exp = invite.expires_at
            if exp.tzinfo is None:
                from datetime import timezone
                exp = exp.replace(tzinfo=timezone.utc)
            invites.append({
                "id": invite.id,
                "email": invite.email,
                "name": invite.name,
                "role": invite.role.value,
                "expires_at": invite.expires_at.isoformat(),
                "expired": exp < now,
            })
        return invites

    async def resend_invite(self, current: Parent, invite_id: int) -> dict:
        return await self._resend_invite_record(current.family_id, invite_id, inviter=current)

    async def resend_invite_for_family(self, family_id: int, invite_id: int) -> dict:
        primary = await self.parents.get_primary(family_id)
        if not primary:
            raise HTTPException(status_code=404, detail="Orang tua utama tidak ditemukan")
        return await self._resend_invite_record(family_id, invite_id, inviter=primary)

    async def _resend_invite_record(self, family_id: int, invite_id: int, *, inviter: Parent) -> dict:
        result = await self.db.execute(
            select(ParentInvite).where(
                ParentInvite.id == invite_id,
                ParentInvite.family_id == family_id,
                ParentInvite.accepted_at.is_(None),
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise HTTPException(status_code=404, detail="Undangan tidak ditemukan")

        exp = invite.expires_at
        if exp.tzinfo is None:
            from datetime import timezone
            exp = exp.replace(tzinfo=timezone.utc)
        raw = generate_raw_token()
        if exp < utcnow():
            invite.token_hash = hash_token(raw)
            invite.expires_at = utcnow() + timedelta(hours=72)
        else:
            # Re-use existing token is not possible without storing raw token; rotate always on resend
            invite.token_hash = hash_token(raw)
            invite.expires_at = utcnow() + timedelta(hours=72)

        fam = await self.db.get(Family, family_id)
        link = f"{settings.frontend_base_url}/accept-invite?token={raw}"
        sent = await send_coparent_invite_email(
            to=invite.email,
            inviter_name=inviter.name,
            family_name=fam.family_name if fam else "Keluarga",
            link=link,
        )
        if not sent:
            logger.info("DEV co-parent invite resend for %s: %s", invite.email, link)
        await self.db.commit()
        if sent:
            return {"message": f"Undangan dikirim ulang ke {invite.email}", "email_sent": True}
        return {
            "message": f"Undangan diperbarui untuk {invite.email}, tetapi email belum terkirim.",
            "email_sent": False,
        }

    async def remove_parent(self, current: Parent, parent_id: int) -> dict:
        target = await self.parents.get_by_id(parent_id)
        if not target or target.family_id != current.family_id:
            raise HTTPException(status_code=404, detail="Orang tua tidak ditemukan")
        if target.is_primary:
            raise HTTPException(status_code=400, detail="Tidak dapat menghapus orang tua utama")
        if target.id != current.id and not current.is_primary:
            raise HTTPException(status_code=403, detail="Hanya orang tua utama yang dapat menghapus co-parent")
        target.is_active = False
        await self.db.commit()
        return {"message": "Co-parent dihapus dari keluarga"}
