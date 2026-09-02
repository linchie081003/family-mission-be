from sqlalchemy import text

from app.core.database import engine


async def run_chat_migrations() -> None:
    statements = [
        "ALTER TABLE children ADD COLUMN IF NOT EXISTS display_name VARCHAR(100)",
        "ALTER TABLE children ALTER COLUMN avatar_url TYPE TEXT",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100)",
        "ALTER TABLE chat_messages ALTER COLUMN child_id DROP NOT NULL",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
