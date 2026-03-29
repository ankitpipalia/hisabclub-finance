"""enable row-level security tenant isolation

Revision ID: b1d2e3f4a5b6
Revises: a9c4e2d1b7f0
Create Date: 2026-03-30 08:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1d2e3f4a5b6"
down_revision: Union[str, None] = "a9c4e2d1b7f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES_WITH_USER_ID = [
    "raw_pdfs",
    "statements",
    "parsed_transactions",
    "canonical_transactions",
    "document_artifacts",
    "document_knowledge_chunks",
    "connected_accounts",
    "raw_sms",
    "transfer_matches",
    "extraction_jobs",
    "sync_cursors",
    "statement_period_coverage",
    "institution_password_patterns",
    "bills",
    "budgets",
    "monthly_summaries",
    "recurring_patterns",
    "user_overrides",
    "user_merchant_rules",
]


def _policy_name(table_name: str) -> str:
    return f"rls_user_scope_{table_name}"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.request_user_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS $$
          SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.is_worker_context()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
          SELECT COALESCE(NULLIF(current_setting('app.worker_mode', true), ''), '0') = '1'
        $$;
        """
    )

    for table in _TABLES_WITH_USER_ID:
        policy = _policy_name(table)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"""
            CREATE POLICY {policy}
            ON {table}
            USING (app.is_worker_context() OR user_id = app.request_user_id())
            WITH CHECK (app.is_worker_context() OR user_id = app.request_user_id())
            """
        )

    # categories has system defaults with user_id IS NULL.
    op.execute("ALTER TABLE categories ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS rls_user_scope_categories ON categories")
    op.execute(
        """
        CREATE POLICY rls_user_scope_categories
        ON categories
        USING (
            app.is_worker_context()
            OR user_id = app.request_user_id()
            OR user_id IS NULL
        )
        WITH CHECK (
            app.is_worker_context()
            OR user_id = app.request_user_id()
            OR user_id IS NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rls_user_scope_categories ON categories")
    op.execute("ALTER TABLE categories DISABLE ROW LEVEL SECURITY")

    for table in _TABLES_WITH_USER_ID:
        policy = _policy_name(table)
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS app.is_worker_context()")
    op.execute("DROP FUNCTION IF EXISTS app.request_user_id()")
