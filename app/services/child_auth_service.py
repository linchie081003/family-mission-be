from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, verify_pin
from app.core.constants import PIN_INVALID
from app.core.security import sanitize_family_code
from app.core.upload_url import resolve_avatar_url
from app.models.models import Child, Family
from app.repositories.child_repository import ChildRepository
from app.repositories.family_repository import FamilyRepository
from app.schemas import ChildListItem, ChildLoginSelect, ChildPinChange, ChildSetPin, TokenResponse


class ChildAuthService:
    """Business logic: child login, PIN setup, and PIN changes."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.families = FamilyRepository(db)
        self.children = ChildRepository(db)

    async def _get_family_by_code(self, family_code: str) -> Family:
        code = sanitize_family_code(family_code)
        family = await self.families.get_by_code(code)
        if not family:
            raise HTTPException(status_code=404, detail="Kode keluarga tidak ditemukan")
        if not family.is_active:
            raise HTTPException(status_code=403, detail="Keluarga belum disetujui Super Admin")
        return family

    async def list_children_for_login(self, family_code: str) -> list[ChildListItem]:
        family = await self._get_family_by_code(family_code)
        children = await self.children.list_active_for_family(family.id)
        return [
            ChildListItem(
                id=c.id,
                name=c.name,
                color=c.color,
                avatar_url=resolve_avatar_url(c.avatar_url),
                has_pin=c.pin_hash is not None,
            )
            for c in children
        ]

    async def _get_child_for_family(self, family: Family, child_id: int) -> Child:
        child = await self.children.get_active_by_id(child_id, family.id)
        if not child:
            raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
        return child

    async def login(self, data: ChildLoginSelect) -> TokenResponse:
        family = await self._get_family_by_code(data.family_code)
        child = await self._get_child_for_family(family, data.child_id)

        if not child.pin_hash:
            raise HTTPException(status_code=400, detail="PIN belum diatur. Atur PIN terlebih dahulu.")
        if not verify_pin(data.pin, child.pin_hash):
            raise HTTPException(status_code=401, detail=PIN_INVALID)

        token = create_access_token({"child_id": child.id, "family_id": family.id, "role": "child"})
        return TokenResponse(access_token=token, role="child", family_id=family.id, child_id=child.id)

    async def first_time_setup(self, data: ChildLoginSelect) -> TokenResponse:
        family = await self._get_family_by_code(data.family_code)
        child = await self._get_child_for_family(family, data.child_id)

        if child.pin_hash:
            raise HTTPException(status_code=400, detail="PIN sudah diatur. Gunakan login biasa.")

        await self.children.set_pin(child, data.pin)
        token = create_access_token({"child_id": child.id, "family_id": family.id, "role": "child"})
        return TokenResponse(access_token=token, role="child", family_id=family.id, child_id=child.id)

    async def setup_pin(self, child: Child, data: ChildSetPin) -> dict:
        if child.pin_hash:
            raise HTTPException(status_code=400, detail="PIN sudah diatur. Gunakan ubah PIN.")
        await self.children.set_pin(child, data.pin)
        return {"message": "PIN berhasil diatur"}

    async def change_pin(self, child: Child, data: ChildPinChange) -> dict:
        if not child.pin_hash or not verify_pin(data.current_pin, child.pin_hash):
            raise HTTPException(status_code=401, detail=PIN_INVALID)
        await self.children.set_pin(child, data.pin)
        return {"message": "PIN berhasil diubah"}

    async def reset_pin(self, family: Family, child_id: int) -> dict:
        child = await self.children.get_by_id(child_id, family.id)
        if not child:
            raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
        await self.children.clear_pin(child)
        return {"message": f"PIN {child.name} berhasil direset. Anak perlu buat PIN baru."}
