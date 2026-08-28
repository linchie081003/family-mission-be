"""Add activation fields, billing tables, platform_broadcasts

Revision ID: 004_super_admin_billing
"""
from alembic import op

revision = "004_super_admin_billing"
down_revision = "003_family_feature_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE families ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE families ADD COLUMN IF NOT EXISTS activation_preset VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE families DROP COLUMN IF EXISTS activation_preset")
    op.execute("ALTER TABLE families DROP COLUMN IF EXISTS activated_at")
