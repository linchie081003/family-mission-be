from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_family
from app.core.upload_url import get_upload_url
from app.database import get_db
from app.models.models import Child, Family
from app.schemas import ChildCreate, ChildPublic, ChildUpdate
from app.services.audit_service import log_audit
from app.services.gamification import get_level
from app.services.points import get_spendable_balance

router = APIRouter(prefix="/children", tags=["children"])


async def child_to_public(child: Child, db: AsyncSession) -> ChildPublic:
    spendable, reward_redeemed = await get_spendable_balance(db, child)
    return ChildPublic(
        id=child.id,
        name=child.name,
        display_name=child.display_name,
        color=child.color,
        weekly_target=child.weekly_target,
        avatar_url=get_upload_url(child.avatar_url),
        lifetime_points=child.lifetime_points,
        active_balance=child.active_balance,
        spendable_balance=spendable,
        reward_redeemed_total=reward_redeemed,
        total_redeemed=child.total_redeemed,
        current_streak=child.current_streak,
        longest_streak=child.longest_streak,
        level=get_level(child.lifetime_points),
        has_pin=child.pin_hash is not None,
    )


@router.get("", response_model=list[ChildPublic])
async def list_children(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Child).where(Child.family_id == family.id, Child.is_active == True).order_by(Child.name)
    )
    children = result.scalars().all()
    return [await child_to_public(c, db) for c in children]


@router.post("", response_model=ChildPublic)
async def create_child(
    data: ChildCreate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child = Child(
        family_id=family.id,
        name=data.name,
        color=data.color,
        weekly_target=data.weekly_target,
    )
    db.add(child)
    await db.flush()
    await log_audit(
        db, family.id, "parent", family.family_name, "create", "child",
        f"Menambah anak: {child.name}", entity_id=child.id,
        details={"name": child.name, "color": child.color, "weekly_target": child.weekly_target},
    )
    return await child_to_public(child, db)


@router.get("/{child_id}", response_model=ChildPublic)
async def get_child(
    child_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Child).where(Child.id == child_id, Child.family_id == family.id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
    return await child_to_public(child, db)


@router.patch("/{child_id}", response_model=ChildPublic)
async def update_child(
    child_id: int,
    data: ChildUpdate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Child).where(Child.id == child_id, Child.family_id == family.id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Anak tidak ditemukan")

    changes = {}
    if data.name is not None:
        changes["name"] = {"from": child.name, "to": data.name}
        child.name = data.name
    if data.display_name is not None:
        cleaned = data.display_name.strip() or None
        changes["display_name"] = {"from": child.display_name, "to": cleaned}
        child.display_name = cleaned
    if data.color is not None:
        changes["color"] = {"from": child.color, "to": data.color}
        child.color = data.color
    if data.weekly_target is not None:
        changes["weekly_target"] = {"from": child.weekly_target, "to": data.weekly_target}
        child.weekly_target = data.weekly_target

    if changes:
        await log_audit(
            db, family.id, "parent", family.family_name, "update", "child",
            f"Memperbarui profil anak: {child.name}", entity_id=child.id, details=changes,
        )

    return await child_to_public(child, db)


@router.delete("/{child_id}")
async def deactivate_child(
    child_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Child).where(Child.id == child_id, Child.family_id == family.id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
    child.is_active = False
    await log_audit(
        db, family.id, "parent", family.family_name, "deactivate", "child",
        f"Menonaktifkan anak: {child.name}", entity_id=child.id,
    )
    return {"message": "Anak dinonaktifkan"}
