from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ChatMessage, Child, Family, NotificationType
from app.services.feature_guard import assert_feature_enabled
from app.services.notification_service import notify_child
from app.websocket.manager import ws_manager


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_children_threads(self, family: Family) -> list[dict]:
        assert_feature_enabled(family, "chat")
        children = await self.db.execute(
            select(Child).where(Child.family_id == family.id, Child.is_active == True)
        )
        threads = []
        for child in children.scalars().all():
            unread = await self.db.scalar(
                select(func.count()).select_from(ChatMessage).where(
                    ChatMessage.family_id == family.id,
                    ChatMessage.child_id == child.id,
                    ChatMessage.sender_role == "child",
                    ChatMessage.read_at.is_(None),
                )
            )
            threads.append({
                "child_id": child.id,
                "child_name": child.name,
                "child_color": child.color,
                "unread_count": unread or 0,
            })
        return threads

    async def get_messages(
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

    async def send_message(
        self,
        family: Family,
        child_id: int,
        sender_role: str,
        body: str,
    ) -> ChatMessage:
        assert_feature_enabled(family, "chat")
        body = body.strip()
        if not body or len(body) > 1000:
            raise HTTPException(status_code=400, detail="Pesan tidak valid")
        await self._verify_child(child_id, family.id)

        msg = ChatMessage(
            family_id=family.id,
            child_id=child_id,
            sender_role=sender_role,
            body=body,
        )
        self.db.add(msg)
        await self.db.flush()

        await ws_manager.broadcast(family.id, {
            "event": "chat_message",
            "child_id": child_id,
            "data": {
                "id": msg.id,
                "sender_role": sender_role,
                "body": body,
                "created_at": msg.created_at.isoformat(),
            },
        })

        if sender_role == "parent":
            child = await self._verify_child(child_id, family.id)
            await notify_child(
                self.db,
                family.id,
                child_id,
                NotificationType.CHAT,
                "Pesan baru dari orang tua",
                body[:120],
                data={"child_id": child_id, "message_id": msg.id},
            )
            await ws_manager.broadcast(family.id, {
                "event": "chat_unread",
                "child_id": child_id,
                "data": {"child_id": child_id},
            })
        else:
            await ws_manager.broadcast(family.id, {
                "event": "chat_unread",
                "child_id": child_id,
                "data": {"child_id": child_id},
            })

        return msg

    async def broadcast_to_children(self, family: Family, body: str) -> dict:
        assert_feature_enabled(family, "chat")
        body = body.strip()
        if not body or len(body) > 1000:
            raise HTTPException(status_code=400, detail="Pesan tidak valid")

        children = await self.db.execute(
            select(Child).where(Child.family_id == family.id, Child.is_active == True)
        )
        child_list = list(children.scalars().all())
        if not child_list:
            raise HTTPException(status_code=400, detail="Belum ada anak aktif")

        sent = []
        for child in child_list:
            msg = await self.send_message(family, child.id, "parent", body)
            sent.append({"child_id": child.id, "message_id": msg.id})
        return {"sent_count": len(sent), "messages": sent}

    async def parent_total_unread(self, family: Family) -> int:
        assert_feature_enabled(family, "chat")
        return await self.db.scalar(
            select(func.count()).select_from(ChatMessage).where(
                ChatMessage.family_id == family.id,
                ChatMessage.sender_role == "child",
                ChatMessage.read_at.is_(None),
            )
        ) or 0

    async def mark_read_parent(self, family: Family, child_id: int) -> int:
        assert_feature_enabled(family, "chat")
        await self._verify_child(child_id, family.id)
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(ChatMessage)
            .where(
                ChatMessage.family_id == family.id,
                ChatMessage.child_id == child_id,
                ChatMessage.sender_role == "child",
                ChatMessage.read_at.is_(None),
            )
            .values(read_at=now)
        )
        count = result.rowcount or 0
        if count:
            await ws_manager.broadcast(family.id, {
                "event": "chat_unread",
                "child_id": child_id,
                "data": {"child_id": child_id, "marked_read": count},
            })
        return count

    async def mark_read_child(self, child: Child, family: Family) -> int:
        assert_feature_enabled(family, "chat")
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(ChatMessage)
            .where(
                ChatMessage.family_id == family.id,
                ChatMessage.child_id == child.id,
                ChatMessage.sender_role == "parent",
                ChatMessage.read_at.is_(None),
            )
            .values(read_at=now)
        )
        count = result.rowcount or 0
        if count:
            await ws_manager.broadcast(family.id, {
                "event": "chat_unread",
                "child_id": child.id,
                "data": {"child_id": child.id, "marked_read": count},
            })
        return count

    async def child_unread_count(self, child: Child, family: Family) -> int:
        assert_feature_enabled(family, "chat")
        return await self.db.scalar(
            select(func.count()).select_from(ChatMessage).where(
                ChatMessage.family_id == family.id,
                ChatMessage.child_id == child.id,
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
