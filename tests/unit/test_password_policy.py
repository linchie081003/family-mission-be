import pytest

from app.core.password_policy import validate_password_strength


def test_password_policy_accepts_strong_password():
    validate_password_strength("Secret123!")


def test_password_policy_rejects_short():
    with pytest.raises(ValueError, match="8 karakter"):
        validate_password_strength("Ab1!")


def test_password_policy_rejects_no_uppercase():
    with pytest.raises(ValueError, match="huruf besar"):
        validate_password_strength("secret123!")


def test_password_policy_rejects_no_special():
    with pytest.raises(ValueError, match="karakter khusus"):
        validate_password_strength("Secret123")
