import pytest
from fastapi import HTTPException

from app.core.auth import create_access_token, decode_access_token, hash_password, verify_password
from app.core.security import sanitize_family_code, validate_upload


class TestPasswordHashing:
    def test_hash_and_verify_password(self):
        hashed = hash_password("my-secret-password")
        assert hashed != "my-secret-password"
        assert verify_password("my-secret-password", hashed)
        assert not verify_password("wrong-password", hashed)


class TestJwt:
    def test_create_and_decode_token(self):
        token = create_access_token({"family_id": 1, "role": "parent"})
        payload = decode_access_token(token)
        assert payload["family_id"] == 1
        assert payload["role"] == "parent"

    def test_invalid_token_raises(self):
        with pytest.raises(HTTPException):
            decode_access_token("not-a-valid-token")


class TestFamilyCodeSanitize:
    def test_valid_code(self):
        assert sanitize_family_code("abc123") == "ABC123"

    def test_rejects_invalid_code(self):
        with pytest.raises(HTTPException):
            sanitize_family_code("ab")

    def test_rejects_special_chars(self):
        with pytest.raises(HTTPException):
            sanitize_family_code("ABC-123")


class TestUploadValidation:
    def test_accepts_valid_png(self):
        validate_upload("photo.png", "image/png", 1024)

    def test_rejects_invalid_extension(self):
        with pytest.raises(HTTPException):
            validate_upload("file.exe", "image/png", 1024)

    def test_rejects_oversized_file(self):
        with pytest.raises(HTTPException):
            validate_upload("photo.png", "image/png", 10 * 1024 * 1024)
