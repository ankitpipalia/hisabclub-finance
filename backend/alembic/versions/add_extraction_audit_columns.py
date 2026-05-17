"""add extraction audit columns to canonical transactions

Revision ID: add_extraction_audit
Revises: c4d5e6f7a8b9
Create Date: 2026-04-27 02:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_extraction_audit"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "canonical_transactions",
        sa.Column("extraction_source", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column("canonical_transactions", sa.Column("extraction_confidence", sa.Float(), nullable=True))
    op.add_column(
        "canonical_transactions",
        sa.Column("source_statement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_canonical_transactions_source_statement_id",
        "canonical_transactions",
        "statements",
        ["source_statement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("canonical_transactions", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column("canonical_transactions", sa.Column("source_char_offset", sa.Integer(), nullable=True))
    op.add_column(
        "canonical_transactions",
        sa.Column("source_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("canonical_transactions", sa.Column("dedup_key", sa.String(length=64), nullable=True))
    op.add_column(
        "canonical_transactions",
        sa.Column("validation_status", sa.String(length=20), nullable=False, server_default="valid"),
    )
    op.add_column(
        "canonical_transactions",
        sa.Column("validation_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("canonical_transactions", sa.Column("balance_walk_passed", sa.Boolean(), nullable=True))
    op.add_column(
        "canonical_transactions",
        sa.Column("review_task_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_canonical_transactions_review_task_id",
        "canonical_transactions",
        "review_tasks",
        ["review_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "canonical_transactions",
        sa.Column("user_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("canonical_transactions", sa.Column("override_reason", sa.Text(), nullable=True))
    op.add_column(
        "canonical_transactions",
        sa.Column("override_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_canonical_transactions_dedup_key",
        "canonical_transactions",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
    )
    op.create_index(
        "ix_canonical_transactions_statement_date",
        "canonical_transactions",
        ["source_statement_id", "transaction_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_canonical_transactions_statement_date", table_name="canonical_transactions")
    op.drop_index("ix_canonical_transactions_dedup_key", table_name="canonical_transactions")
    op.drop_column("canonical_transactions", "override_at")
    op.drop_column("canonical_transactions", "override_reason")
    op.drop_column("canonical_transactions", "user_override")
    op.drop_constraint(
        "fk_canonical_transactions_review_task_id",
        "canonical_transactions",
        type_="foreignkey",
    )
    op.drop_column("canonical_transactions", "review_task_id")
    op.drop_column("canonical_transactions", "balance_walk_passed")
    op.drop_column("canonical_transactions", "validation_errors")
    op.drop_column("canonical_transactions", "validation_status")
    op.drop_column("canonical_transactions", "dedup_key")
    op.drop_column("canonical_transactions", "source_evidence")
    op.drop_column("canonical_transactions", "source_char_offset")
    op.drop_column("canonical_transactions", "source_page_number")
    op.drop_constraint(
        "fk_canonical_transactions_source_statement_id",
        "canonical_transactions",
        type_="foreignkey",
    )
    op.drop_column("canonical_transactions", "source_statement_id")
    op.drop_column("canonical_transactions", "extraction_confidence")
    op.drop_column("canonical_transactions", "extraction_source")
