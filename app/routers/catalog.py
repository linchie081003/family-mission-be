from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_family
from app.database import get_db
from app.models.models import Family, Punishment, Reward
from app.schemas import PunishmentCreate, PunishmentPublic, RewardCreate, RewardPublic

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/punishments", response_model=list[PunishmentPublic])
async def list_punishments(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Punishment).where(Punishment.family_id == family.id, Punishment.is_active == True))
    return result.scalars().all()


@router.post("/punishments", response_model=PunishmentPublic)
async def create_punishment(
    data: PunishmentCreate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    p = Punishment(family_id=family.id, title=data.title, points_deducted=data.points_deducted)
    db.add(p)
    await db.flush()
    return p


@router.delete("/punishments/{punishment_id}")
async def delete_punishment(
    punishment_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Punishment).where(Punishment.id == punishment_id, Punishment.family_id == family.id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404)
    p.is_active = False
    return {"message": "Punishment dinonaktifkan"}


@router.get("/rewards", response_model=list[RewardPublic])
async def list_rewards(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Reward).where(Reward.family_id == family.id, Reward.is_active == True))
    return result.scalars().all()


@router.post("/rewards", response_model=RewardPublic)
async def create_reward(
    data: RewardCreate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    r = Reward(family_id=family.id, title=data.title, description=data.description, points_cost=data.points_cost)
    db.add(r)
    await db.flush()
    return r


@router.delete("/rewards/{reward_id}")
async def delete_reward(
    reward_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Reward).where(Reward.id == reward_id, Reward.family_id == family.id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404)
    r.is_active = False
    return {"message": "Reward dinonaktifkan"}
