from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _engine_connect_args() -> dict:
    url = settings.database_url.lower()
    if "supabase" in url or "ssl=require" in url:
        return {"ssl": "require"}
    return {}


engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=_engine_connect_args(),
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
