"""Add is_demo on subscriptions and payment proof/verification fields

Revision ID: 006_billing_enhancements
Revises: 005_billing_tables
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006_billing_enhancements"
down_revision: Union[str, None] = "005_billing_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscriptions_is_demo ON subscriptions (is_demo)")
    op.execute(
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS proof_image_url VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS rejection_reason TEXT"
    )
    op.execute(
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ"
    )
    op.execute(
        """
        ALTER TABLE payments
        ADD COLUMN IF NOT EXISTS verified_by_admin_id INTEGER
        REFERENCES platform_admins(id)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS verified_by_admin_id")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS verified_at")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS rejection_reason")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS proof_image_url")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_is_demo")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS is_demo")
