import pytest
from pydantic import ValidationError

from app.schemas import QuizQuestionInput

SAMPLE_QUESTION = {
    "question": "Berapa 2 + 2?",
    "options": ["3", "4", "5"],
    "correct_index": 1,
    "explanation": "2 + 2 = 4",
}


class TestQuizQuestionValidation:
    def test_accepts_valid_question(self):
        q = QuizQuestionInput(**SAMPLE_QUESTION)
        assert q.correct_index == 1
        assert len(q.options) == 3

    def test_rejects_correct_index_out_of_range(self):
        with pytest.raises(ValidationError):
            QuizQuestionInput(question="Test?", options=["A", "B"], correct_index=5)

    def test_rejects_too_few_options(self):
        with pytest.raises(ValidationError):
            QuizQuestionInput(question="Test?", options=["A"], correct_index=0)

    def test_strips_empty_options(self):
        with pytest.raises(ValidationError):
            QuizQuestionInput(question="Test?", options=["A", "  "], correct_index=0)
