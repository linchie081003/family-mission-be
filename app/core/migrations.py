from sqlalchemy import text

from app.core.database import engine


async def run_light_migrations() -> None:
    statements = [
        "ALTER TABLE platform_admins ADD COLUMN IF NOT EXISTS notification_email VARCHAR(255)",
        "ALTER TABLE quiz_templates ADD COLUMN IF NOT EXISTS sub_material VARCHAR(200)",
        "ALTER TABLE quiz_template_questions ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)",
        "ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS sub_material VARCHAR(200)",
        "ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS questions_per_attempt INTEGER",
        "ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS target_all_children BOOLEAN DEFAULT TRUE",
        "ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)",
        """
        CREATE TABLE IF NOT EXISTS quiz_child_targets (
            quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
            child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            PRIMARY KEY (quiz_id, child_id)
        )
        """,
        "ALTER TABLE quiz_questions ALTER COLUMN image_url TYPE TEXT",
        "ALTER TABLE quiz_template_questions ALTER COLUMN image_url TYPE TEXT",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
