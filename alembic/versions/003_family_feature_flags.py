"""Add family feature flags for rewards and mission evidence

Revision ID: 003_family_feature_flags
Revises: 002_quiz_target_not_null
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_family_feature_flags"
down_revision: Union[str, None] = "002_quiz_target_all_children_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("families", sa.Column("rewards_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("families", sa.Column("mission_evidence_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("families", sa.Column("daily_mission_limit", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE families
        SET rewards_enabled = TRUE,
            mission_evidence_enabled = TRUE,
            daily_mission_limit = NULL
    """)


def downgrade() -> None:
    op.drop_column("families", "daily_mission_limit")
    op.drop_column("families", "mission_evidence_enabled")
    op.drop_column("families", "rewards_enabled")
