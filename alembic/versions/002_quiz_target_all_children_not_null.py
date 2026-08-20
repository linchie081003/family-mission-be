"""Enforce quizzes.target_all_children NOT NULL

Revision ID: 002_quiz_target_not_null
Revises: 001_parent_multiparent
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_quiz_target_not_null"
down_revision: Union[str, None] = "001_parent_multiparent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE quizzes SET target_all_children = TRUE WHERE target_all_children IS NULL")
    op.alter_column(
        "quizzes",
        "target_all_children",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
    )


def downgrade() -> None:
    op.alter_column(
        "quizzes",
        "target_all_children",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=sa.text("true"),
    )
