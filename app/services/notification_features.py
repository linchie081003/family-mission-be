from sqlalchemy import ColumnElement

from app.models.models import Family, Notification, NotificationType

# Notification types gated by family feature flags (None = always allowed).
NOTIFICATION_TYPE_FEATURES: dict[NotificationType, str | None] = {
    NotificationType.CHAT: "chat_enabled",
    NotificationType.AGENDA: "agenda_enabled",
    NotificationType.QUIZ: "quiz_enabled",
    NotificationType.REDEMPTION_PENDING: "rewards_enabled",
    NotificationType.REDEMPTION_APPROVED: "rewards_enabled",
    NotificationType.REDEMPTION_REJECTED: "rewards_enabled",
    NotificationType.ACHIEVEMENT: "rewards_enabled",
    NotificationType.PUNISHMENT: "rewards_enabled",
}


def is_notification_type_allowed(family: Family, ntype: NotificationType) -> bool:
    attr = NOTIFICATION_TYPE_FEATURES.get(ntype)
    if not attr:
        return True
    return bool(getattr(family, attr, False))


def allowed_notification_types(family: Family) -> list[NotificationType]:
    return [t for t in NotificationType if is_notification_type_allowed(family, t)]


def notification_type_filter(family: Family) -> ColumnElement[bool]:
    allowed = allowed_notification_types(family)
    return Notification.type.in_(allowed)
