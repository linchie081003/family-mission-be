from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_family
from app.database import get_db
from app.models.models import Family, Mission, MissionCategory, MissionDifficulty
from app.schemas import MissionCreate, MissionPublic, MissionUpdate

router = APIRouter(prefix="/missions", tags=["missions"])


def mission_to_public(m: Mission) -> MissionPublic:
    return MissionPublic(
        id=m.id,
        title=m.title,
        description=m.description,
        category=m.category.value,
        points=m.points,
        difficulty=m.difficulty.value,
        is_active=m.is_active,
        sort_order=m.sort_order,
    )


@router.get("", response_model=list[MissionPublic])
async def list_missions(
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = None,
):
    query = select(Mission).where(Mission.family_id == family.id).order_by(Mission.sort_order, Mission.id)
    if category:
        query = query.where(Mission.category == MissionCategory(category))
    result = await db.execute(query)
    return [mission_to_public(m) for m in result.scalars().all()]


@router.post("", response_model=MissionPublic)
async def create_mission(
    data: MissionCreate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    mission = Mission(
        family_id=family.id,
        title=data.title,
        description=data.description,
        category=MissionCategory(data.category),
        points=data.points,
        difficulty=MissionDifficulty(data.difficulty),
    )
    db.add(mission)
    await db.flush()
    return mission_to_public(mission)


@router.patch("/{mission_id}", response_model=MissionPublic)
async def update_mission(
    mission_id: int,
    data: MissionUpdate,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Mission).where(Mission.id == mission_id, Mission.family_id == family.id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Misi tidak ditemukan")

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "difficulty" and value:
            setattr(mission, field, MissionDifficulty(value))
        else:
            setattr(mission, field, value)

    return mission_to_public(mission)


@router.delete("/{mission_id}")
async def delete_mission(
    mission_id: int,
    family: Annotated[Family, Depends(get_current_family)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Mission).where(Mission.id == mission_id, Mission.family_id == family.id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Misi tidak ditemukan")
    mission.is_active = False
    return {"message": "Misi dinonaktifkan"}
