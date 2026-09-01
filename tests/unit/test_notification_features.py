from app.models.models import Family, NotificationType
from app.services.notification_features import (
    allowed_notification_types,
    is_notification_type_allowed,
)


def _family(**flags: bool) -> Family:
    return Family(
        id=1,
        email="a@b.c",
        family_name="Test",
        family_code="ABC123",
        password_hash="x",
        chat_enabled=flags.get("chat_enabled", False),
        agenda_enabled=flags.get("agenda_enabled", False),
        quiz_enabled=flags.get("quiz_enabled", False),
        rewards_enabled=flags.get("rewards_enabled", True),
    )


def test_chat_blocked_when_disabled():
    family = _family(chat_enabled=False)
    assert is_notification_type_allowed(family, NotificationType.CHAT) is False
    assert is_notification_type_allowed(family, NotificationType.MISSION_PENDING) is True


def test_chat_allowed_when_enabled():
    family = _family(chat_enabled=True)
    assert is_notification_type_allowed(family, NotificationType.CHAT) is True


def test_redemption_requires_rewards():
    family = _family(rewards_enabled=False)
    assert is_notification_type_allowed(family, NotificationType.REDEMPTION_PENDING) is False


def test_allowed_types_excludes_disabled():
    family = _family(chat_enabled=False, quiz_enabled=False, agenda_enabled=False)
    allowed = allowed_notification_types(family)
    assert NotificationType.CHAT not in allowed
    assert NotificationType.QUIZ not in allowed
    assert NotificationType.AGENDA not in allowed
    assert NotificationType.MISSION_PENDING in allowed
