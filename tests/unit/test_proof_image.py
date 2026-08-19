import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas import QuizQuestionInput
from app.services.proof_image import normalize_image_data_url, validate_proof_image


class TestProofImage:
    def test_requires_image_when_required(self):
        with pytest.raises(HTTPException) as exc:
            validate_proof_image(None, required=True)
        assert exc.value.status_code == 400

    def test_allows_empty_when_optional(self):
        assert validate_proof_image(None, required=False) is None

    def test_rejects_invalid_format(self):
        with pytest.raises(HTTPException):
            validate_proof_image("not-base64", required=True)

    def test_accepts_valid_data_uri(self):
        value = "data:image/png;base64,iVBORw0KGgo="
        assert validate_proof_image(value, required=True) == value

    def test_rejects_oversized_payload(self):
        huge = "data:image/png;base64," + ("A" * 500_000)
        with pytest.raises(HTTPException):
            validate_proof_image(huge, required=True)

    def test_accepts_legacy_upload_path(self):
        value = "/uploads/quiz_old.jpg"
        assert normalize_image_data_url(value, required=False) == value


class TestQuizQuestionImage:
    def _question(self, **kwargs):
        payload = {
            "question": "Test?",
            "options": ["A", "B"],
            "correct_index": 0,
            **kwargs,
        }
        return QuizQuestionInput(**payload)

    def test_accepts_valid_base64_image(self):
        q = self._question(image_url="data:image/jpeg;base64,/9j/4AAQ")
        assert q.image_url == "data:image/jpeg;base64,/9j/4AAQ"

    def test_accepts_legacy_upload_path(self):
        q = self._question(image_url="/uploads/quiz.jpg")
        assert q.image_url == "/uploads/quiz.jpg"

    def test_rejects_invalid_image_format(self):
        with pytest.raises(ValidationError):
            self._question(image_url="not-an-image")

    def test_allows_no_image(self):
        q = self._question(image_url=None)
        assert q.image_url is None
