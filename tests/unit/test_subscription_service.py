import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from app.services.plan_presets import BASIC_PRESET, FAMILY_PRESET, apply_plan_features
from app.services.subscription_service import SubscriptionService


def test_basic_preset_has_mission_limit():
    assert BASIC_PRESET["daily_mission_limit"] == 5
    assert BASIC_PRESET["rewards_enabled"] is True
    assert BASIC_PRESET["quiz_enabled"] is False


def test_family_preset_full_features():
    assert FAMILY_PRESET["chat_enabled"] is True
    assert FAMILY_PRESET["agenda_enabled"] is True


class _FakeFamily:
    def __init__(self):
        self.rewards_enabled = False
        self.mission_evidence_enabled = False
        self.quiz_enabled = False
        self.chat_enabled = False
        self.agenda_enabled = False
        self.daily_mission_limit = None
        self.is_active = False


class _FakePlan:
    slug = "basic"
    feature_preset = BASIC_PRESET


def test_apply_plan_features_sets_active():
    family = _FakeFamily()
    apply_plan_features(family, _FakePlan())
    assert family.is_active is True
    assert family.daily_mission_limit == 5


@pytest.mark.asyncio
async def test_assign_demo_plan_sets_flags():
    family = MagicMock()
    family.id = 1
    family.activated_at = None
    family.is_active = False
    family.activation_preset = None

    plan = MagicMock()
    plan.id = 3
    plan.slug = "family"
    plan.feature_preset = {}

    sub = MagicMock()
    sub.is_demo = False
    sub.status = "trial"
    sub.manual_notes = None

    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[plan, sub])
    db.get = AsyncMock(return_value=plan)
    db.flush = AsyncMock()

    svc = SubscriptionService(db)
    result = await svc.assign_demo_plan(family, "family", note="test demo")

    assert result.is_demo is True
    assert result.status == "active"
    assert result.current_period_end is None
    assert family.activation_preset == "family"


@pytest.mark.asyncio
async def test_check_and_expire_trials_skips_demo():
    from app.core.tokens import utcnow

    sub = MagicMock()
    sub.is_demo = True
    sub.status = "trial"
    sub.trial_ends_at = utcnow() - timedelta(days=1)

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sub)

    svc = SubscriptionService(db)
    expired = await svc.check_and_expire_trials(1)

    assert expired is False
