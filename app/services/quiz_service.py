from datetime import datetime, timezone
import random

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Child,
    Family,
    NotificationType,
    Quiz,
    QuizAttempt,
    QuizChildTarget,
    QuizQuestion,
    QuizTemplate,
    QuizTemplateQuestion,
    TransactionType,
)
from app.schemas import (
    FamilyQuizCreate,
    FamilyQuizUpdate,
    QuizAnswerSubmit,
    QuizQuestionInput,
    QuizTemplateCreate,
    QuizTemplateUpdate,
)
from app.services.feature_guard import assert_feature_enabled
from app.services.notification_service import notify_child
from app.services.points import (
    broadcast_child_update,
    get_daily_points_earned,
    record_transaction,
)


async def seed_default_templates(db: AsyncSession) -> None:
    existing = await db.scalar(select(func.count()).select_from(QuizTemplate))
    if existing and existing > 0:
        return

    templates = [
        {
            "subject": "Matematika",
            "title": "Penjumlahan Dasar",
            "grade_level": "SD",
            "questions": [
                ("Berapa 5 + 3?", ["6", "7", "8", "9"], 2, "5 + 3 = 8"),
                ("Berapa 12 - 4?", ["6", "7", "8", "9"], 2, "12 - 4 = 8"),
            ],
        },
        {
            "subject": "IPA",
            "title": "Bagian Tubuh Manusia",
            "grade_level": "SD",
            "questions": [
                ("Organ untuk bernapas?", ["Jantung", "Paru-paru", "Lambung", "Hati"], 1, "Paru-paru"),
                ("Organ pompa darah?", ["Jantung", "Ginjal", "Usus", "Otak"], 0, "Jantung"),
            ],
        },
        {
            "subject": "Bahasa Indonesia",
            "title": "Kata Baku",
            "grade_level": "SD",
            "questions": [
                ("Kata baku dari 'aktip'?", ["Aktip", "Aktif", "Active", "Aktiv"], 1, "Aktif"),
            ],
        },
    ]

    for tpl in templates:
        template = QuizTemplate(
            subject=tpl["subject"],
            title=tpl["title"],
            grade_level=tpl["grade_level"],
            description=f"Template {tpl['title']}",
        )
        db.add(template)
        await db.flush()
        for i, (q, opts, correct, expl) in enumerate(tpl["questions"]):
            db.add(QuizTemplateQuestion(
                template_id=template.id,
                question=q,
                options=opts,
                correct_index=correct,
                explanation=expl,
                sort_order=i,
            ))


class QuizService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_templates(self) -> list[QuizTemplate]:
        result = await self.db.execute(
            select(QuizTemplate).where(QuizTemplate.is_active == True).order_by(QuizTemplate.subject)
        )
        return list(result.scalars().all())

    async def list_all_templates_admin(self) -> list[QuizTemplate]:
        result = await self.db.execute(select(QuizTemplate).order_by(QuizTemplate.subject, QuizTemplate.title))
        return list(result.scalars().all())

    async def set_template_active(self, template_id: int, is_active: bool) -> QuizTemplate:
        tpl = await self.db.get(QuizTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template tidak ditemukan")
        tpl.is_active = is_active
        await self.db.flush()
        return tpl

    async def get_template(self, template_id: int) -> dict:
        tpl = await self.db.get(QuizTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template tidak ditemukan")
        questions_result = await self.db.execute(
            select(QuizTemplateQuestion)
            .where(QuizTemplateQuestion.template_id == template_id)
            .order_by(QuizTemplateQuestion.sort_order)
        )
        questions = list(questions_result.scalars().all())
        return {
            "id": tpl.id,
            "subject": tpl.subject,
            "title": tpl.title,
            "description": tpl.description,
            "sub_material": tpl.sub_material,
            "grade_level": tpl.grade_level,
            "is_active": tpl.is_active,
            "questions": [
                {
                    "id": q.id,
                    "question": q.question,
                    "image_url": q.image_url,
                    "options": q.options,
                    "correct_index": q.correct_index,
                    "explanation": q.explanation,
                    "sort_order": q.sort_order,
                }
                for q in questions
            ],
        }

    async def _assigned_child_ids(self, quiz_id: int) -> list[int]:
        result = await self.db.execute(
            select(QuizChildTarget.child_id).where(QuizChildTarget.quiz_id == quiz_id)
        )
        return list(result.scalars().all())

    async def _sync_child_targets(self, quiz_id: int, family_id: int, target_all: bool, child_ids: list[int]) -> None:
        await self.db.execute(delete(QuizChildTarget).where(QuizChildTarget.quiz_id == quiz_id))
        if target_all or not child_ids:
            return
        for cid in child_ids:
            child = await self.db.scalar(
                select(Child.id).where(Child.id == cid, Child.family_id == family_id, Child.is_active == True)
            )
            if child:
                self.db.add(QuizChildTarget(quiz_id=quiz_id, child_id=cid))

    async def _child_can_access_quiz(self, quiz: Quiz, child_id: int) -> bool:
        if quiz.target_all_children:
            return True
        result = await self.db.scalar(
            select(func.count()).select_from(QuizChildTarget).where(
                QuizChildTarget.quiz_id == quiz.id,
                QuizChildTarget.child_id == child_id,
            )
        )
        return bool(result)

    def _pick_questions(self, questions: list[QuizQuestion], per_attempt: int | None) -> list[QuizQuestion]:
        pool = list(questions)
        if per_attempt and per_attempt < len(pool):
            return random.sample(pool, per_attempt)
        return pool

    async def create_template(self, data: QuizTemplateCreate) -> dict:
        template = QuizTemplate(
            subject=data.subject.strip(),
            title=data.title.strip(),
            description=data.description,
            sub_material=data.sub_material,
            grade_level=data.grade_level.strip(),
        )
        self.db.add(template)
        await self.db.flush()
        self._add_template_questions(template.id, data.questions)
        await self.db.flush()
        return await self.get_template(template.id)

    async def update_template(self, template_id: int, data: QuizTemplateUpdate) -> dict:
        tpl = await self._get_template_with_questions(template_id)
        tpl.subject = data.subject.strip()
        tpl.title = data.title.strip()
        tpl.description = data.description
        tpl.sub_material = data.sub_material
        tpl.grade_level = data.grade_level.strip()
        await self.db.execute(
            delete(QuizTemplateQuestion).where(QuizTemplateQuestion.template_id == template_id)
        )
        await self.db.flush()
        self._add_template_questions(template_id, data.questions)
        await self.db.flush()
        return await self.get_template(template_id)

    async def delete_template(self, template_id: int) -> dict:
        tpl = await self.db.get(QuizTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template tidak ditemukan")
        cloned = await self.db.scalar(
            select(func.count()).select_from(Quiz).where(Quiz.template_id == template_id)
        )
        if cloned and cloned > 0:
            tpl.is_active = False
            await self.db.flush()
            return {"id": tpl.id, "deleted": False, "is_active": False, "message": "Template dinonaktifkan (sudah dipakai keluarga)"}
        await self.db.delete(tpl)
        await self.db.flush()
        return {"id": template_id, "deleted": True, "message": "Template dihapus"}

    async def get_family_quiz(self, family: Family, quiz_id: int) -> dict:
        assert_feature_enabled(family, "quiz")
        quiz = await self._get_quiz_with_questions(quiz_id, family.id, active_only=False)
        questions_result = await self.db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.sort_order)
        )
        questions = list(questions_result.scalars().all())
        assigned = await self._assigned_child_ids(quiz_id)
        return {
            "id": quiz.id,
            "subject": quiz.subject,
            "title": quiz.title,
            "sub_material": quiz.sub_material,
            "points_reward": quiz.points_reward,
            "passing_score": quiz.passing_score,
            "questions_per_attempt": quiz.questions_per_attempt,
            "target_all_children": quiz.target_all_children,
            "assigned_child_ids": assigned,
            "is_active": quiz.is_active,
            "template_id": quiz.template_id,
            "questions": [
                {
                    "id": q.id,
                    "question": q.question,
                    "image_url": q.image_url,
                    "options": q.options,
                    "correct_index": q.correct_index,
                    "explanation": q.explanation,
                    "sort_order": q.sort_order,
                }
                for q in questions
            ],
        }

    async def create_family_quiz(self, family: Family, data: FamilyQuizCreate) -> dict:
        assert_feature_enabled(family, "quiz")
        if data.questions_per_attempt and data.questions_per_attempt > len(data.questions):
            raise HTTPException(status_code=400, detail="Soal per attempt melebihi bank soal")
        quiz = Quiz(
            family_id=family.id,
            subject=data.subject.strip(),
            title=data.title.strip(),
            sub_material=data.sub_material,
            points_reward=data.points_reward,
            passing_score=data.passing_score,
            questions_per_attempt=data.questions_per_attempt,
            target_all_children=data.target_all_children,
        )
        self.db.add(quiz)
        await self.db.flush()
        self._add_quiz_questions(quiz.id, data.questions)
        await self._sync_child_targets(quiz.id, family.id, data.target_all_children, data.assigned_child_ids)
        await self.db.flush()
        return await self.get_family_quiz(family, quiz.id)

    async def update_family_quiz(self, family: Family, quiz_id: int, data: FamilyQuizUpdate) -> dict:
        assert_feature_enabled(family, "quiz")
        if data.questions_per_attempt and data.questions_per_attempt > len(data.questions):
            raise HTTPException(status_code=400, detail="Soal per attempt melebihi bank soal")
        quiz = await self._get_quiz_with_questions(quiz_id, family.id, active_only=False)
        quiz.subject = data.subject.strip()
        quiz.title = data.title.strip()
        quiz.sub_material = data.sub_material
        quiz.points_reward = data.points_reward
        quiz.passing_score = data.passing_score
        quiz.questions_per_attempt = data.questions_per_attempt
        quiz.target_all_children = data.target_all_children
        await self.db.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id))
        await self.db.flush()
        self._add_quiz_questions(quiz.id, data.questions)
        await self._sync_child_targets(quiz.id, family.id, data.target_all_children, data.assigned_child_ids)
        await self.db.flush()
        return await self.get_family_quiz(family, quiz_id)

    async def set_family_quiz_active(self, family: Family, quiz_id: int, is_active: bool) -> dict:
        assert_feature_enabled(family, "quiz")
        quiz = await self._get_quiz_with_questions(quiz_id, family.id, active_only=False)
        quiz.is_active = is_active
        await self.db.flush()
        return self._quiz_to_dict(quiz)

    async def list_family_quizzes_for_parent(self, family: Family) -> list[dict]:
        assert_feature_enabled(family, "quiz")
        result = await self.db.execute(
            select(Quiz).where(Quiz.family_id == family.id).order_by(Quiz.is_active.desc(), Quiz.subject)
        )
        items = []
        for q in result.scalars().all():
            pool_size = await self.db.scalar(
                select(func.count()).select_from(QuizQuestion).where(QuizQuestion.quiz_id == q.id)
            )
            assigned = await self._assigned_child_ids(q.id)
            items.append({
                "id": q.id,
                "subject": q.subject,
                "title": q.title,
                "sub_material": q.sub_material,
                "points_reward": q.points_reward,
                "passing_score": q.passing_score,
                "question_pool_size": pool_size or 0,
                "questions_per_attempt": q.questions_per_attempt,
                "target_all_children": q.target_all_children,
                "assigned_child_ids": assigned,
                "is_active": q.is_active,
                "template_id": q.template_id,
            })
        return items

    def _add_template_questions(self, template_id: int, questions: list[QuizQuestionInput]) -> None:
        for i, q in enumerate(questions):
            self.db.add(QuizTemplateQuestion(
                template_id=template_id,
                question=q.question.strip(),
                image_url=q.image_url,
                options=q.options,
                correct_index=q.correct_index,
                explanation=q.explanation,
                sort_order=i,
            ))

    def _add_quiz_questions(self, quiz_id: int, questions: list[QuizQuestionInput]) -> None:
        for i, q in enumerate(questions):
            self.db.add(QuizQuestion(
                quiz_id=quiz_id,
                question=q.question.strip(),
                image_url=q.image_url,
                options=q.options,
                correct_index=q.correct_index,
                explanation=q.explanation,
                sort_order=i,
            ))

    async def _get_template_with_questions(self, template_id: int) -> QuizTemplate:
        result = await self.db.execute(
            select(QuizTemplate)
            .options(selectinload(QuizTemplate.questions))
            .where(QuizTemplate.id == template_id)
        )
        tpl = result.scalar_one_or_none()
        if not tpl:
            raise HTTPException(status_code=404, detail="Template tidak ditemukan")
        return tpl

    async def _get_quiz_with_questions(self, quiz_id: int, family_id: int, *, active_only: bool) -> Quiz:
        query = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(Quiz.id == quiz_id, Quiz.family_id == family_id)
        )
        if active_only:
            query = query.where(Quiz.is_active == True)
        result = await self.db.execute(query)
        quiz = result.scalar_one_or_none()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz tidak ditemukan")
        return quiz

    def _template_to_dict(self, tpl: QuizTemplate) -> dict:
        questions = sorted(tpl.questions, key=lambda q: q.sort_order)
        return {
            "id": tpl.id,
            "subject": tpl.subject,
            "title": tpl.title,
            "description": tpl.description,
            "grade_level": tpl.grade_level,
            "is_active": tpl.is_active,
            "questions": [
                {
                    "id": q.id,
                    "question": q.question,
                    "options": q.options,
                    "correct_index": q.correct_index,
                    "explanation": q.explanation,
                    "sort_order": q.sort_order,
                }
                for q in questions
            ],
        }

    def _quiz_to_dict(self, quiz: Quiz) -> dict:
        questions = sorted(quiz.questions, key=lambda q: q.sort_order)
        return {
            "id": quiz.id,
            "subject": quiz.subject,
            "title": quiz.title,
            "points_reward": quiz.points_reward,
            "passing_score": quiz.passing_score,
            "is_active": quiz.is_active,
            "template_id": quiz.template_id,
            "questions": [
                {
                    "id": q.id,
                    "question": q.question,
                    "options": q.options,
                    "correct_index": q.correct_index,
                    "explanation": q.explanation,
                    "sort_order": q.sort_order,
                }
                for q in questions
            ],
        }

    async def clone_template(self, family: Family, template_id: int, points_reward: int = 10, passing_score: int = 70) -> Quiz:
        assert_feature_enabled(family, "quiz")
        tpl = await self.db.get(QuizTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template tidak ditemukan")
        questions = await self.db.execute(
            select(QuizTemplateQuestion).where(QuizTemplateQuestion.template_id == template_id).order_by(QuizTemplateQuestion.sort_order)
        )
        quiz = Quiz(
            family_id=family.id,
            template_id=template_id,
            subject=tpl.subject,
            title=tpl.title,
            sub_material=tpl.sub_material,
            points_reward=points_reward,
            passing_score=passing_score,
        )
        self.db.add(quiz)
        await self.db.flush()
        for q in questions.scalars().all():
            self.db.add(QuizQuestion(
                quiz_id=quiz.id,
                question=q.question,
                image_url=q.image_url,
                options=q.options,
                correct_index=q.correct_index,
                explanation=q.explanation,
                sort_order=q.sort_order,
            ))
        return quiz

    async def list_family_quizzes(self, family: Family) -> list[Quiz]:
        assert_feature_enabled(family, "quiz")
        result = await self.db.execute(
            select(Quiz).where(Quiz.family_id == family.id, Quiz.is_active == True).order_by(Quiz.subject)
        )
        return list(result.scalars().all())

    async def list_child_quizzes(self, child: Child, family: Family) -> list[dict]:
        assert_feature_enabled(family, "quiz")
        quizzes = await self.list_family_quizzes(family)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        items = []
        for quiz in quizzes:
            if not await self._child_can_access_quiz(quiz, child.id):
                continue
            passed_today = await self.db.scalar(
                select(func.count()).select_from(QuizAttempt).where(
                    QuizAttempt.child_id == child.id,
                    QuizAttempt.quiz_id == quiz.id,
                    QuizAttempt.passed == True,
                    QuizAttempt.completed_at >= today_start,
                )
            )
            pool_size = await self.db.scalar(
                select(func.count()).select_from(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)
            )
            attempt_count = quiz.questions_per_attempt or pool_size or 0
            items.append({
                "id": quiz.id,
                "subject": quiz.subject,
                "title": quiz.title,
                "sub_material": quiz.sub_material,
                "points_reward": quiz.points_reward,
                "passing_score": quiz.passing_score,
                "question_pool_size": pool_size or 0,
                "questions_per_attempt": attempt_count,
                "completed_today": bool(passed_today),
            })
        return items

    async def get_quiz_for_child(self, child: Child, family: Family, quiz_id: int) -> dict:
        assert_feature_enabled(family, "quiz")
        quiz = await self._get_quiz_in_family(quiz_id, family.id)
        if not await self._child_can_access_quiz(quiz, child.id):
            raise HTTPException(status_code=404, detail="Quiz tidak ditemukan")
        questions_result = await self.db.execute(
            select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.sort_order)
        )
        all_questions = list(questions_result.scalars().all())
        picked = self._pick_questions(all_questions, quiz.questions_per_attempt)
        random.shuffle(picked)
        display = []
        for q in picked:
            opts = list(q.options)
            random.shuffle(opts)
            display.append({
                "id": q.id,
                "question": q.question,
                "image_url": q.image_url,
                "options": opts,
            })
        return {
            "id": quiz.id,
            "title": quiz.title,
            "subject": quiz.subject,
            "sub_material": quiz.sub_material,
            "passing_score": quiz.passing_score,
            "points_reward": quiz.points_reward,
            "question_pool_size": len(all_questions),
            "questions_per_attempt": len(display),
            "questions": display,
        }

    async def submit_quiz(
        self, child: Child, family: Family, quiz_id: int, answers: list[QuizAnswerSubmit]
    ) -> dict:
        assert_feature_enabled(family, "quiz")
        quiz = await self._get_quiz_in_family(quiz_id, family.id)
        if not await self._child_can_access_quiz(quiz, child.id):
            raise HTTPException(status_code=404, detail="Quiz tidak ditemukan")
        if not answers:
            raise HTTPException(status_code=400, detail="Jawaban wajib diisi")

        questions_result = await self.db.execute(
            select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)
        )
        q_map = {q.id: q for q in questions_result.scalars().all()}
        if not q_map:
            raise HTTPException(status_code=400, detail="Quiz tidak memiliki soal")

        correct = 0
        for ans in answers:
            q = q_map.get(ans.question_id)
            if not q:
                raise HTTPException(status_code=400, detail="Soal tidak valid")
            expected = q.options[q.correct_index] if q.correct_index < len(q.options) else ""
            is_correct = ans.selected_option.strip() == expected.strip()
            if is_correct:
                correct += 1

        total = len(answers)
        score = int(correct / total * 100) if total else 0
        passed = score >= quiz.passing_score

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        already_passed = await self.db.scalar(
            select(func.count()).select_from(QuizAttempt).where(
                QuizAttempt.child_id == child.id,
                QuizAttempt.quiz_id == quiz.id,
                QuizAttempt.passed == True,
                QuizAttempt.completed_at >= today_start,
            )
        )

        points_awarded = 0
        if passed and not already_passed:
            daily_earned = await get_daily_points_earned(self.db, child.id)
            remaining = max(0, family.daily_point_limit - daily_earned)
            points_awarded = min(quiz.points_reward, remaining)
            if points_awarded > 0:
                await record_transaction(
                    self.db, child, family, TransactionType.QUIZ, points_awarded,
                    f"Quiz: {quiz.title}",
                    reference_id=quiz.id,
                )
                await notify_child(
                    self.db, family.id, child.id, NotificationType.QUIZ,
                    "Quiz lulus! 🎉",
                    f"{quiz.title} — +{points_awarded} poin",
                    data={"quiz_id": quiz.id, "points": points_awarded},
                )
                await broadcast_child_update(
                    family.id, child.id, "quiz_passed",
                    {"quiz_title": quiz.title, "points": points_awarded, "score": score},
                )

        attempt = QuizAttempt(
            child_id=child.id,
            quiz_id=quiz.id,
            score=score,
            total_questions=total,
            passed=passed,
            points_awarded=points_awarded,
        )
        self.db.add(attempt)

        return {
            "score": score,
            "passed": passed,
            "points_awarded": points_awarded,
            "points_reward": quiz.points_reward,
            "passing_score": quiz.passing_score,
            "already_passed_today": bool(already_passed),
            "correct_count": correct,
            "total_questions": total,
        }

    async def _get_quiz_in_family(self, quiz_id: int, family_id: int) -> Quiz:
        result = await self.db.execute(
            select(Quiz).where(Quiz.id == quiz_id, Quiz.family_id == family_id, Quiz.is_active == True)
        )
        quiz = result.scalar_one_or_none()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz tidak ditemukan")
        return quiz

    async def list_attempts(self, family: Family) -> list[dict]:
        assert_feature_enabled(family, "quiz")
        result = await self.db.execute(
            select(QuizAttempt, Quiz, Child)
            .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
            .join(Child, QuizAttempt.child_id == Child.id)
            .where(Quiz.family_id == family.id)
            .order_by(QuizAttempt.completed_at.desc())
            .limit(100)
        )
        return [
            {
                "id": a.id,
                "child_name": c.name,
                "quiz_title": q.title,
                "score": a.score,
                "passed": a.passed,
                "points_awarded": a.points_awarded,
                "completed_at": a.completed_at.isoformat(),
            }
            for a, q, c in result.all()
        ]
