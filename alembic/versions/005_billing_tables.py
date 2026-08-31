"""Add billing tables, platform_payment_settings, seed plans

Revision ID: 005_billing_tables
Revises: 004_super_admin_billing
"""
import json
from typing import Sequence, Union

from alembic import op

revision: str = "005_billing_tables"
down_revision: Union[str, None] = "004_super_admin_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLANS = (
    {
        "slug": "basic",
        "name": "Basic",
        "description": "Misi & poin dasar — gratis",
        "price_monthly": 0,
        "price_yearly": 0,
        "trial_days": 0,
        "sort_order": 0,
        "feature_preset": {
            "rewards_enabled": True,
            "mission_evidence_enabled": False,
            "quiz_enabled": False,
            "chat_enabled": False,
            "agenda_enabled": False,
            "daily_mission_limit": 5,
        },
    },
    {
        "slug": "standard",
        "name": "Standard",
        "description": "Misi tanpa batas, bukti foto, quiz edukasi",
        "price_monthly": 29000,
        "price_yearly": 290000,
        "trial_days": 0,
        "sort_order": 1,
        "feature_preset": {
            "rewards_enabled": True,
            "mission_evidence_enabled": True,
            "quiz_enabled": True,
            "chat_enabled": False,
            "agenda_enabled": False,
            "daily_mission_limit": None,
        },
    },
    {
        "slug": "family",
        "name": "Family",
        "description": "Semua fitur Standard + chat keluarga + agenda",
        "price_monthly": 49000,
        "price_yearly": 490000,
        "trial_days": 10,
        "sort_order": 2,
        "feature_preset": {
            "rewards_enabled": True,
            "mission_evidence_enabled": True,
            "quiz_enabled": True,
            "chat_enabled": True,
            "agenda_enabled": True,
            "daily_mission_limit": None,
        },
    },
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id SERIAL PRIMARY KEY,
            slug VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            price_monthly INTEGER NOT NULL DEFAULT 0,
            price_yearly INTEGER NOT NULL DEFAULT 0,
            currency VARCHAR(3) NOT NULL DEFAULT 'IDR',
            trial_days INTEGER NOT NULL DEFAULT 14,
            feature_preset JSONB NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL UNIQUE REFERENCES families(id) ON DELETE CASCADE,
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            status VARCHAR(20) NOT NULL DEFAULT 'trial',
            trial_ends_at TIMESTAMPTZ,
            current_period_start TIMESTAMPTZ,
            current_period_end TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            cancel_reason TEXT,
            manual_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
            subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
            amount INTEGER NOT NULL,
            currency VARCHAR(3) NOT NULL DEFAULT 'IDR',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            provider VARCHAR(30) NOT NULL DEFAULT 'manual',
            provider_ref VARCHAR(200),
            invoice_number VARCHAR(50),
            description TEXT,
            paid_at TIMESTAMPTZ,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS platform_broadcasts (
            id SERIAL PRIMARY KEY,
            platform_admin_id INTEGER NOT NULL REFERENCES platform_admins(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            body TEXT NOT NULL,
            target VARCHAR(20) NOT NULL DEFAULT 'all_active',
            families_reached INTEGER NOT NULL DEFAULT 0,
            send_email BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS platform_payment_settings (
            id SERIAL PRIMARY KEY,
            qris_image_url VARCHAR(500),
            qris_merchant_name VARCHAR(200),
            bank_name VARCHAR(100),
            bank_account_number VARCHAR(50),
            bank_account_holder VARCHAR(100),
            transfer_instructions TEXT,
            payment_methods_enabled JSONB NOT NULL DEFAULT '{"qris_static": true, "bank_transfer": true}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        """
        INSERT INTO platform_payment_settings (id, payment_methods_enabled)
        SELECT 1, '{"qris_static": true, "bank_transfer": true}'::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM platform_payment_settings WHERE id = 1)
        """
    )

    for plan in _PLANS:
        preset = json.dumps(plan["feature_preset"]).replace("'", "''")
        op.execute(f"""
            INSERT INTO plans (slug, name, description, price_monthly, price_yearly, currency,
                trial_days, feature_preset, is_active, sort_order)
            VALUES (
                '{plan["slug"]}', '{plan["name"]}', '{plan["description"]}',
                {plan["price_monthly"]}, {plan["price_yearly"]}, 'IDR',
                {plan["trial_days"]}, '{preset}'::jsonb, TRUE, {plan["sort_order"]}
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                price_monthly = EXCLUDED.price_monthly,
                price_yearly = EXCLUDED.price_yearly,
                trial_days = EXCLUDED.trial_days,
                feature_preset = EXCLUDED.feature_preset,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW()
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_payment_settings")
    op.execute("DROP TABLE IF EXISTS platform_broadcasts")
    op.execute("DROP TABLE IF EXISTS payments")
    op.execute("DROP TABLE IF EXISTS subscriptions")
    op.execute("DROP TABLE IF EXISTS plans")
