"""Migration entrypoint — avoids broken DO-block appended to migrations.py on disk."""

from app.core.migrations import _seed_default_plans
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
        "UPDATE quizzes SET target_all_children = TRUE WHERE target_all_children IS NULL",
        "ALTER TABLE quizzes ALTER COLUMN target_all_children SET DEFAULT TRUE",
        """
        DO $$ BEGIN
            ALTER TABLE quizzes ALTER COLUMN target_all_children SET NOT NULL;
        EXCEPTION WHEN undefined_column THEN NULL;
        END $$;
        """,
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
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS referral_code VARCHAR(8)",
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS referred_by_family_id INTEGER REFERENCES families(id) ON DELETE SET NULL",
        """
        CREATE TABLE IF NOT EXISTS parents (
            id SERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'father',
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            email_verified BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            terms_accepted_at TIMESTAMPTZ,
            privacy_accepted_at TIMESTAMPTZ,
            parental_consent_at TIMESTAMPTZ,
            child_data_protection_accepted_at TIMESTAMPTZ,
            legal_doc_version VARCHAR(20),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_parents_family_id ON parents (family_id)",
        "CREATE INDEX IF NOT EXISTS ix_parents_email ON parents (email)",
        """
        CREATE TABLE IF NOT EXISTS email_tokens (
            id SERIAL PRIMARY KEY,
            parent_id INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL,
            purpose VARCHAR(30) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_email_tokens_parent_id ON email_tokens (parent_id)",
        "CREATE INDEX IF NOT EXISTS ix_email_tokens_token_hash ON email_tokens (token_hash)",
        """
        CREATE TABLE IF NOT EXISTS parent_invites (
            id SERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
            invited_by_parent_id INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            name VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS referral_invites (
            id SERIAL PRIMARY KEY,
            referrer_family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
            invitee_email VARCHAR(255) NOT NULL,
            referral_code VARCHAR(8) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_families_referral_code ON families (referral_code) WHERE referral_code IS NOT NULL",
        """
        DO $$ BEGIN
            ALTER TABLE parents ALTER COLUMN role TYPE VARCHAR(20) USING lower(role::text);
        EXCEPTION WHEN undefined_table THEN NULL;
                 WHEN undefined_column THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
            ALTER TABLE parent_invites ALTER COLUMN role TYPE VARCHAR(20) USING lower(role::text);
        EXCEPTION WHEN undefined_table THEN NULL;
                 WHEN undefined_column THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
            ALTER TABLE email_tokens ALTER COLUMN purpose TYPE VARCHAR(30) USING lower(purpose::text);
        EXCEPTION WHEN undefined_table THEN NULL;
                 WHEN undefined_column THEN NULL;
        END $$;
        """,
        "DROP TYPE IF EXISTS parentrole",
        "DROP TYPE IF EXISTS emailtokenpurpose",
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS rewards_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS mission_evidence_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS daily_mission_limit INTEGER",
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ",
        "ALTER TABLE families ADD COLUMN IF NOT EXISTS activation_preset VARCHAR(20)",
        """
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
        """,
        """
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
        """,
        """
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
        """,
        """
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
        """,
        """
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
        """,
        """
        INSERT INTO platform_payment_settings (id, payment_methods_enabled)
        SELECT 1, '{"qris_static": true, "bank_transfer": true}'::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM platform_payment_settings WHERE id = 1)
        """,
        """
        UPDATE platform_payment_settings
        SET payment_methods_enabled = '{"qris_static": true, "bank_transfer": true}'::jsonb
        WHERE payment_methods_enabled IS NULL
        """,
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_is_demo ON subscriptions (is_demo)",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS proof_image_url VARCHAR(500)",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS rejection_reason TEXT",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ",
        """
        ALTER TABLE payments
        ADD COLUMN IF NOT EXISTS verified_by_admin_id INTEGER
        REFERENCES platform_admins(id)
        """,
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            INSERT INTO parents (
                family_id, email, password_hash, name, role, is_primary,
                email_verified, is_active, created_at
            )
            SELECT
                f.id, f.email, f.password_hash, f.family_name, 'father', TRUE,
                TRUE, TRUE, f.created_at
            FROM families f
            WHERE NOT EXISTS (
                SELECT 1 FROM parents p WHERE p.family_id = f.id AND p.is_primary = TRUE
            )
        """))
        await conn.execute(text("""
            UPDATE families
            SET referral_code = UPPER(SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT) FROM 1 FOR 8))
            WHERE referral_code IS NULL
        """))
        await conn.execute(text("""
            UPDATE families f
            SET rewards_enabled = TRUE,
                mission_evidence_enabled = TRUE,
                daily_mission_limit = NULL
            WHERE f.rewards_enabled = FALSE
              AND f.mission_evidence_enabled = FALSE
              AND (
                EXISTS (
                    SELECT 1 FROM children c
                    WHERE c.family_id = f.id AND c.lifetime_points > 0
                )
                OR EXISTS (
                    SELECT 1 FROM mission_completions mc
                    JOIN children c ON c.id = mc.child_id
                    WHERE c.family_id = f.id AND mc.status = 'APPROVED'
                )
              )
        """))
        await conn.execute(text("""
            UPDATE families SET activated_at = created_at
            WHERE activated_at IS NULL
              AND (
                rewards_enabled = TRUE
                OR mission_evidence_enabled = TRUE
                OR quiz_enabled = TRUE
                OR chat_enabled = TRUE
                OR agenda_enabled = TRUE
                OR EXISTS (SELECT 1 FROM children c WHERE c.family_id = families.id)
              )
        """))
        await _seed_default_plans(conn)
