from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ChatMessage, Child, Family, NotificationType, Parent
from app.services.feature_guard import assert_feature_enabled
from app.services.notification_service import notify_child
from app.websocket.manager import ws_manager


def child_display_name(child: Child) -> str:
    return (child.display_name or child.name).strip() or child.name


def message_to_dict(msg: ChatMessage, *, child_color: str | None = None) -> dict:
    return {
        "id": msg.id,
        "sender_role": msg.sender_role,
        "sender_name": msg.sender_name,
        "child_id": msg.child_id,
        "child_color": child_color,
        "body": msg.body,
        "created_at": msg.created_at.isoformat(),
        "read_at": msg.read_at.isoformat() if msg.read_at else None,
    }


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_family_messages(
        self,
        family: Family,
        *,
        limit: int = 100,
        before_id: int | None = None,
    ) -> list[dict]:
        assert_feature_enabled(family, "chat")
        q = (
            select(ChatMessage)
            .where(ChatMessage.family_id == family.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(min(limit, 200))
        )
        if before_id:
            q = q.where(ChatMessage.id < before_id)
        result = await self.db.execute(q)
        messages = list(reversed(result.scalars().all()))

        child_colors: dict[int, str] = {}
        child_ids = {m.child_id for m in messages if m.child_id}
        if child_ids:
            rows = await self.db.execute(select(Child).where(Child.id.in_(child_ids)))
            for child in rows.scalars().all():
                child_colors[child.id] = child.color

        return [
            message_to_dict(
                m,
                child_color=child_colors.get(m.child_id) if m.child_id else None,
            )
            for m in messages
        ]

    async def list_children_threads(self, family: Family) -> list[dict]:
        assert_feature_enabled(family, "chat")
        unread = await self.parent_total_unread(family)
        children = await self.db.execute(
            select(Child).where(Child.family_id == family.id, Child.is_active == True)
        )
        return [{
            "child_id": 0,
            "child_name": "Chat Keluarga",
            "child_color": "#6366f1",
            "unread_count": unread,
        }] + [{
            "child_id": child.id,
            "child_name": child_display_name(child),
            "child_color": child.color,
            "unread_count": 0,
        } for child in children.scalars().all()]

    async def get_messages(
        self,
        family: Family,
        child_id: int,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[ChatMessage]:
        return await self._get_legacy_messages(family, child_id, limit=limit, before_id=before_id)

    async def _get_legacy_messages(
        self,
        family: Family,
        child_id: int,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[ChatMessage]:
        assert_feature_enabled(family, "chat")
        await self._verify_child(child_id, family.id)
        q = (
            select(ChatMessage)
            .where(ChatMessage.family_id == family.id, ChatMessage.child_id == child_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(min(limit, 100))
        )
        if before_id:
            q = q.where(ChatMessage.id < before_id)
        result = await self.db.execute(q)
        return list(reversed(result.scalars().all()))

    async def send_family_message(
        self,
        family: Family,
        *,
        sender_role: str,
        body: str,
        child: Child | None = None,
        parent: Parent | None = None,
    ) -> ChatMessage:
        assert_feature_enabled(family, "chat")
        body = body.strip()
        if not body or len(body) > 1000:
            raise HTTPException(status_code=400, detail="Pesan tidak valid")

        if sender_role == "child":
            if not child:
                raise HTTPException(status_code=400, detail="Pengirim tidak valid")
            sender_name = child_display_name(child)
            child_id = child.id
        elif sender_role == "parent":
            if not parent:
                raise HTTPException(status_code=400, detail="Pengirim tidak valid")
            sender_name = parent.name
            child_id = None
        else:
            raise HTTPException(status_code=400, detail="Peran pengirim tidak valid")

        msg = ChatMessage(
            family_id=family.id,
            child_id=child_id,
            sender_role=sender_role,
            sender_name=sender_name,
            body=body,
        )
        self.db.add(msg)
        await self.db.flush()

        payload = message_to_dict(
            msg,
            child_color=child.color if child else None,
        )
        await ws_manager.broadcast(family.id, {
            "event": "chat_message",
            "child_id": child_id,
            "data": payload,
        })

        if sender_role == "parent":
            children = await self.db.execute(
                select(Child).where(Child.family_id == family.id, Child.is_active == True)
            )
            for active_child in children.scalars().all():
                await notify_child(
                    self.db,
                    family.id,
                    active_child.id,
                    NotificationType.CHAT,
                    "Pesan baru di chat keluarga",
                    body[:120],
                    data={"message_id": msg.id},
                )
        await ws_manager.broadcast(family.id, {"event": "chat_unread", "data": {}})
        return msg

    async def send_message(
        self,
        family: Family,
        child_id: int,
        sender_role: str,
        body: str,
        *,
        parent: Parent | None = None,
        child: Child | None = None,
    ) -> ChatMessage:
        if sender_role == "parent" and parent:
            return await self.send_family_message(family, sender_role="parent", body=body, parent=parent)
        if sender_role == "child":
            if not child:
                child = await self._verify_child(child_id, family.id)
            return await self.send_family_message(family, sender_role="child", body=body, child=child)
        raise HTTPException(status_code=400, detail="Pengirim tidak valid")

    async def broadcast_to_children(self, family: Family, body: str, *, parent: Parent) -> dict:
        msg = await self.send_family_message(family, sender_role="parent", body=body, parent=parent)
        return {"sent_count": 1, "messages": [{"message_id": msg.id}]}

    async def parent_total_unread(self, family: Family) -> int:
        assert_feature_enabled(family, "chat")
        return await self.db.scalar(
            select(func.count()).select_from(ChatMessage).where(
                ChatMessage.family_id == family.id,
                ChatMessage.sender_role == "child",
                ChatMessage.read_at.is_(None),
            )
        ) or 0

    async def mark_read_parent(self, family: Family, child_id: int = 0) -> int:
        assert_feature_enabled(family, "chat")
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(ChatMessage)
            .where(
                ChatMessage.family_id == family.id,
                ChatMessage.sender_role == "child",
                ChatMessage.read_at.is_(None),
            )
            .values(read_at=now)
        )
        count = result.rowcount or 0
        if count:
            await ws_manager.broadcast(family.id, {"event": "chat_unread", "data": {"marked_read": count}})
        return count

    async def mark_read_child(self, child: Child, family: Family) -> int:
        assert_feature_enabled(family, "chat")
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(ChatMessage)
            .where(
                ChatMessage.family_id == family.id,
                ChatMessage.sender_role == "parent",
                ChatMessage.read_at.is_(None),
            )
            .values(read_at=now)
        )
        count = result.rowcount or 0
        if count:
            await ws_manager.broadcast(family.id, {"event": "chat_unread", "data": {"marked_read": count}})
        return count

    async def child_unread_count(self, child: Child, family: Family) -> int:
        assert_feature_enabled(family, "chat")
        return await self.db.scalar(
            select(func.count()).select_from(ChatMessage).where(
                ChatMessage.family_id == family.id,
                ChatMessage.sender_role == "parent",
                ChatMessage.read_at.is_(None),
            )
        ) or 0

    async def _verify_child(self, child_id: int, family_id: int) -> Child:
        result = await self.db.execute(
            select(Child).where(Child.id == child_id, Child.family_id == family_id, Child.is_active == True)
        )
        child = result.scalar_one_or_none()
        if not child:
            raise HTTPException(status_code=404, detail="Anak tidak ditemukan")
        return child
