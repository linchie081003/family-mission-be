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
        # --- Multi-parent & auth features ---
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
        # Normalize enum columns created by SQLAlchemy create_all to VARCHAR (values: father/mother/guardian)
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
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))

        # Migrate existing families to parents (one-time)
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

        # Generate referral codes for families missing them
        await conn.execute(text("""
            UPDATE families
            SET referral_code = UPPER(SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT) FROM 1 FOR 8))
            WHERE referral_code IS NULL
        """))
