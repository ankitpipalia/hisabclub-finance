"""create runtime rls role and grants

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-03-30 09:05:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hisabclub_rls') THEN
                CREATE ROLE hisabclub_rls
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS;
            END IF;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Could not create role hisabclub_rls';
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            GRANT hisabclub_rls TO CURRENT_USER;
            GRANT USAGE ON SCHEMA public TO hisabclub_rls;
            GRANT USAGE ON SCHEMA app TO hisabclub_rls;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hisabclub_rls;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hisabclub_rls;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hisabclub_rls;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT USAGE, SELECT ON SEQUENCES TO hisabclub_rls;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Could not grant runtime role permissions';
        END $$;
        """
    )


def downgrade() -> None:
    # Keep role/grants by default to avoid breaking running services.
    pass
