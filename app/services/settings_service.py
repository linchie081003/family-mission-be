from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password, verify_password
from app.models.models import Family, Parent
from app.repositories.settings_repository import AuditRepository, SettingsRepository
from app.schemas import FamilyPublic, ParentPasswordChange, SettingsUpdate
from app.services.audit_service import log_audit


class SettingsService:
    """Business logic: family settings, password change, audit trail."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings_repo = SettingsRepository(db)

    async def update_settings(self, family: Family, data: SettingsUpdate) -> Family:
        old_rupiah = family.rupiah_per_point
        old_limit = family.daily_point_limit
        old_min_cash = family.min_cash_redemption
        changed = False

        if data.rupiah_per_point is not None:
            family.rupiah_per_point = data.rupiah_per_point
            changed = True
        if data.daily_point_limit is not None:
            family.daily_point_limit = data.daily_point_limit
            changed = True
        if data.min_cash_redemption is not None:
            family.min_cash_redemption = data.min_cash_redemption
            changed = True

        if not changed:
            return family

        await self.settings_repo.add_history(
            family_id=family.id,
            rupiah_per_point=family.rupiah_per_point,
            daily_point_limit=family.daily_point_limit,
            min_cash_redemption=family.min_cash_redemption,
            note=data.note,
        )

        if data.rupiah_per_point is not None and family.rupiah_per_point != old_rupiah:
            await log_audit(
                self.db, family.id, "parent", family.family_name, "update", "settings",
                f"Mengubah nilai rupiah per poin: Rp{old_rupiah} → Rp{family.rupiah_per_point}",
                details={
                    "field": "rupiah_per_point",
                    "previous": old_rupiah,
                    "current": family.rupiah_per_point,
                    "note": data.note,
                },
            )

        if data.daily_point_limit is not None and family.daily_point_limit != old_limit:
            await log_audit(
                self.db, family.id, "parent", family.family_name, "update", "settings",
                f"Mengubah batas maks poin harian: {old_limit} → {family.daily_point_limit}",
                details={
                    "field": "daily_point_limit",
                    "previous": old_limit,
                    "current": family.daily_point_limit,
                    "note": data.note,
                },
            )

        if data.min_cash_redemption is not None and family.min_cash_redemption != old_min_cash:
            await log_audit(
                self.db, family.id, "parent", family.family_name, "update", "settings",
                f"Mengubah minimal poin tukar uang: {old_min_cash} → {family.min_cash_redemption} poin",
                details={
                    "field": "min_cash_redemption",
                    "previous": old_min_cash,
                    "current": family.min_cash_redemption,
                    "note": data.note,
                },
            )

        return family

    async def change_password(self, parent: Parent, data: ParentPasswordChange) -> dict:
        if not verify_password(data.current_password, parent.password_hash):
            raise HTTPException(status_code=400, detail="Password saat ini salah")
        if data.current_password == data.new_password:
            raise HTTPException(status_code=400, detail="Password baru harus berbeda")

        parent.password_hash = hash_password(data.new_password)
        family = await self.db.get(Family, parent.family_id)
        await log_audit(
            self.db, parent.family_id, "parent", parent.name, "update", "parent_password",
            "Password orang tua diubah",
            details={"changed_at": "now", "parent_id": parent.id},
        )
        return {"message": "Password berhasil diubah"}

    async def get_history(self, family_id: int):
        return await self.settings_repo.list_history(family_id)


class AuditService:
    def __init__(self, db: AsyncSession):
        self.repo = AuditRepository(db)

    async def list_parent_logs(self, family_id: int, limit: int = 100):
        return await self.repo.list_parent_visible(family_id, limit)
