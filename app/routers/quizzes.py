from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Family
from app.schemas import FamilyQuizCreate, FamilyQuizDetailPublic, FamilyQuizUpdate
from app.services.feature_guard import require_feature
from app.services.quiz_service import QuizService, seed_default_templates

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


class CloneTemplateRequest(BaseModel):
    points_reward: int = Field(default=10, ge=1)
    passing_score: int = Field(default=70, ge=50, le=100)


class QuizActiveUpdate(BaseModel):
    is_active: bool


@router.get("/templates")
async def list_templates(
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await seed_default_templates(db)
    templates = await QuizService(db).list_templates()
    return [{"id": t.id, "subject": t.subject, "title": t.title, "grade_level": t.grade_level} for t in templates]


@router.get("/attempts")
async def list_attempts(
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await QuizService(db).list_attempts(family)


@router.post("/from-template/{template_id}")
async def clone_template(
    template_id: int,
    data: CloneTemplateRequest,
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    quiz = await QuizService(db).clone_template(
        family, template_id, data.points_reward, data.passing_score
    )
    return {"id": quiz.id, "title": quiz.title, "message": "Quiz berhasil ditambahkan"}


@router.get("")
async def list_quizzes(
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await QuizService(db).list_family_quizzes_for_parent(family)


@router.post("", response_model=FamilyQuizDetailPublic)
async def create_quiz(
    data: FamilyQuizCreate,
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await QuizService(db).create_family_quiz(family, data)


@router.get("/{quiz_id}", response_model=FamilyQuizDetailPublic)
async def get_quiz(
    quiz_id: int,
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await QuizService(db).get_family_quiz(family, quiz_id)


@router.put("/{quiz_id}", response_model=FamilyQuizDetailPublic)
async def update_quiz(
    quiz_id: int,
    data: FamilyQuizUpdate,
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await QuizService(db).update_family_quiz(family, quiz_id, data)


@router.patch("/{quiz_id}")
async def patch_quiz(
    quiz_id: int,
    data: QuizActiveUpdate,
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    quiz = await QuizService(db).set_family_quiz_active(family, quiz_id, data.is_active)
    return {"id": quiz["id"], "is_active": quiz["is_active"]}


@router.delete("/{quiz_id}")
async def delete_quiz(
    quiz_id: int,
    family: Annotated[Family, Depends(require_feature("quiz"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    quiz = await QuizService(db).set_family_quiz_active(family, quiz_id, False)
    return {"id": quiz["id"], "is_active": False, "message": "Quiz dinonaktifkan"}
