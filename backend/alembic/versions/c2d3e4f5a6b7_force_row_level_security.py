"""force row level security for tenant-scoped tables

Revision ID: c2d3e4f5a6b7
Revises: b1d2e3f4a5b6
Create Date: 2026-03-30 08:20:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = [
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
    "categories",
]


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
