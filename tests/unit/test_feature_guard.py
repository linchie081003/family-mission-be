import pytest
from fastapi import HTTPException

from app.models.models import Family
from app.services.feature_guard import assert_rewards_enabled, assert_feature_enabled


def test_assert_rewards_enabled_blocks():
    family = Family(
        id=1,
        email="a@b.com",
        password_hash="x",
        family_name="Test",
        family_code="ABC123",
        rewards_enabled=False,
    )
    with pytest.raises(HTTPException) as exc:
        assert_rewards_enabled(family)
    assert exc.value.status_code == 403


def test_assert_rewards_enabled_allows():
    family = Family(
        id=1,
        email="a@b.com",
        password_hash="x",
        family_name="Test",
        family_code="ABC123",
        rewards_enabled=True,
    )
    assert_rewards_enabled(family)


def test_mission_evidence_feature_label():
    family = Family(
        id=1,
        email="a@b.com",
        password_hash="x",
        family_name="Test",
        family_code="ABC123",
        mission_evidence_enabled=False,
    )
    with pytest.raises(HTTPException) as exc:
        assert_feature_enabled(family, "mission_evidence")
    assert "Bukti Misi" in exc.value.detail
