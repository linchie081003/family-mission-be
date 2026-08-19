"""Backward-compatible re-exports. Use app.core.database in new code."""

from app.core.database import Base, async_session, engine, get_db  # noqa: F401
