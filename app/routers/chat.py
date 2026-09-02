from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_parent
from app.database import get_db
from app.models.models import Family, Parent
from app.services.chat_service import ChatService
from app.services.feature_guard import require_feature

router = APIRouter(prefix="/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class BroadcastMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


@router.get("/family/messages")
async def get_family_messages(
    family: Annotated[Family, Depends(require_feature("chat"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=200),
    before_id: int | None = None,
):
    return await ChatService(db).get_family_messages(family, limit=limit, before_id=before_id)


@router.post("/family/messages")
async def send_family_message(
    data: SendMessageRequest,
    family: Annotated[Family, Depends(require_feature("chat"))],
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    msg = await ChatService(db).send_family_message(
        family, sender_role="parent", body=data.body, parent=parent,
    )
    return {"id": msg.id, "created_at": msg.created_at.isoformat()}


@router.post("/family/read")
async def mark_family_read(
    family: Annotated[Family, Depends(require_feature("chat"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    count = await ChatService(db).mark_read_parent(family)
    return {"marked_read": count}


@router.get("/children")
async def list_threads(
    family: Annotated[Family, Depends(require_feature("chat"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ChatService(db).list_children_threads(family)


@router.get("/unread-count")
async def chat_unread_count(
    family: Annotated[Family, Depends(require_feature("chat"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    count = await ChatService(db).parent_total_unread(family)
    return {"count": count}


@router.post("/broadcast")
async def broadcast_message(
    data: BroadcastMessageRequest,
    family: Annotated[Family, Depends(require_feature("chat"))],
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ChatService(db).broadcast_to_children(family, data.body, parent=parent)


@router.get("/{child_id}/messages")
async def get_messages(
    child_id: int,
    family: Annotated[Family, Depends(require_feature("chat"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    before_id: int | None = None,
):
    if child_id == 0:
        return await ChatService(db).get_family_messages(family, limit=limit, before_id=before_id)
    messages = await ChatService(db).get_messages(family, child_id, limit=limit, before_id=before_id)
    return [
        {
            "id": m.id,
            "sender_role": m.sender_role,
            "sender_name": m.sender_name,
            "child_id": m.child_id,
            "body": m.body,
            "created_at": m.created_at.isoformat(),
            "read_at": m.read_at.isoformat() if m.read_at else None,
        }
        for m in messages
    ]


@router.post("/{child_id}/messages")
async def send_message(
    child_id: int,
    data: SendMessageRequest,
    family: Annotated[Family, Depends(require_feature("chat"))],
    parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if child_id == 0:
        msg = await ChatService(db).send_family_message(
            family, sender_role="parent", body=data.body, parent=parent,
        )
    else:
        msg = await ChatService(db).send_message(
            family, child_id, "parent", data.body, parent=parent,
        )
    return {"id": msg.id, "created_at": msg.created_at.isoformat()}


@router.post("/{child_id}/read")
async def mark_read(
    child_id: int,
    family: Annotated[Family, Depends(require_feature("chat"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    count = await ChatService(db).mark_read_parent(family, child_id)
    return {"marked_read": count}
