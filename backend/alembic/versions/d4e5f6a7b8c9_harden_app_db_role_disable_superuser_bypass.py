"""harden app db role disable superuser bypass

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-03-30 08:35:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            is_super boolean;
        BEGIN
            SELECT r.rolsuper INTO is_super
            FROM pg_roles r
            WHERE r.rolname = current_user;
            IF COALESCE(is_super, false) THEN
                BEGIN
                    EXECUTE format(
                        'ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
                        current_user
                    );
                EXCEPTION
                    WHEN insufficient_privilege OR feature_not_supported THEN
                        RAISE NOTICE 'Could not harden role %, continuing.', current_user;
                END;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Intentionally no-op: security hardening should remain in place.
    pass
