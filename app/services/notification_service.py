from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification, NotificationType, RecipientRole
from app.websocket.manager import ws_manager


async def push_notification(
    db: AsyncSession,
    family_id: int,
    recipient_role: RecipientRole,
    type: NotificationType,
    title: str,
    body: str,
    child_id: int | None = None,
    data: dict | None = None,
    commit: bool = False,
) -> Notification:
    notification = Notification(
        family_id=family_id,
        recipient_role=recipient_role,
        child_id=child_id,
        type=type,
        title=title,
        body=body,
        data=data,
    )
    db.add(notification)
    await db.flush()

    await ws_manager.broadcast(family_id, {
        "event": "notification",
        "child_id": child_id,
        "data": {
            "id": notification.id,
            "type": type.value,
            "title": title,
            "body": body,
            "recipient_role": recipient_role.value,
            "child_id": child_id,
            "data": data,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        },
    })

    if commit:
        await db.commit()

    return notification


async def notify_parent(
    db: AsyncSession,
    family_id: int,
    type: NotificationType,
    title: str,
    body: str,
    child_id: int | None = None,
    data: dict | None = None,
) -> Notification:
    return await push_notification(
        db, family_id, RecipientRole.PARENT, type, title, body, child_id=child_id, data=data
    )


async def notify_child(
    db: AsyncSession,
    family_id: int,
    child_id: int,
    type: NotificationType,
    title: str,
    body: str,
    data: dict | None = None,
) -> Notification:
    return await push_notification(
        db, family_id, RecipientRole.CHILD, type, title, body, child_id=child_id, data=data
    )
