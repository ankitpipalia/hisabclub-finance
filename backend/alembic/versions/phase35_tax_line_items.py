# ruff: noqa: E501
"""Phase 3.5 — normalised tax line-item tables for line-level reconciliation.

Revision ID: phase35_tax_line_items
Revises: phase3_review_nullable_statement
Create Date: 2026-05-20 22:00:00.000000

Adds four new tables:

  - ais_line_items
  - form26as_line_items
  - form16_items
  - tax_reconciliation_matches

Each follows the RLS pattern established in
`b1d2e3f4a5b6_enable_row_level_security_tenant_isolation.py`: the `user_id`
column gates access via `app.request_user_id()` / `app.is_worker_context()`.

Aggregate-only reconcilers (`engines/tax/reconcile/{ais,form_26as,form16}.py`)
continue to work; line-item reconcilers are introduced in Sprint B.3 and
take precedence when these tables are populated.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "phase35_tax_line_items"
down_revision: Union[str, None] = "phase3_review_nullable_statement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = (
    "ais_line_items",
    "form26as_line_items",
    "form16_items",
    "tax_reconciliation_matches",
)


def _enable_rls(table: str) -> None:
    policy = f"rls_user_scope_{table}"
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


def upgrade() -> None:
    # ----- ais_line_items -----
    op.create_table(
        "ais_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fy", sa.String(10), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("sub_category", sa.String(120), nullable=True),
        sa.Column("deductor_name", sa.Text(), nullable=True),
        sa.Column("deductor_pan", sa.String(20), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("info_source", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column(
            "evidence_doc_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_row", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ais_line_items_user_fy", "ais_line_items", ["user_id", "fy"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_ais_line_items_idempotency
        ON ais_line_items (
            user_id,
            fy,
            category,
            COALESCE(sub_category, ''),
            COALESCE(deductor_pan, ''),
            COALESCE(info_source, ''),
            amount
        )
        """
    )
    _enable_rls("ais_line_items")

    # ----- form26as_line_items -----
    op.create_table(
        "form26as_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fy", sa.String(10), nullable=False),
        sa.Column("part", sa.String(8), nullable=False),  # "A", "A1", "B", "C", ...
        sa.Column("deductor_tan", sa.String(20), nullable=True),
        sa.Column("deductor_name", sa.Text(), nullable=True),
        sa.Column("section", sa.String(20), nullable=True),  # "192", "194A", ...
        sa.Column("amount_credit", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_tds", sa.Numeric(14, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column(
            "evidence_doc_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_row", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_form26as_line_items_user_fy", "form26as_line_items", ["user_id", "fy"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_form26as_line_items_idempotency
        ON form26as_line_items (
            user_id,
            fy,
            part,
            COALESCE(deductor_tan, ''),
            COALESCE(section, ''),
            COALESCE(amount_tds, 0),
            COALESCE(amount_credit, 0)
        )
        """
    )
    _enable_rls("form26as_line_items")

    # ----- form16_items -----
    op.create_table(
        "form16_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fy", sa.String(10), nullable=False),
        sa.Column("employer_name", sa.Text(), nullable=True),
        sa.Column("employer_tan", sa.String(20), nullable=True),
        sa.Column("head", sa.String(40), nullable=False),  # "gross_salary" | "tds" | "deduction_80c" | ...
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "evidence_doc_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_row", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_form16_items_user_fy", "form16_items", ["user_id", "fy"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_form16_items_idempotency
        ON form16_items (
            user_id,
            fy,
            COALESCE(employer_tan, ''),
            COALESCE(employer_name, ''),
            head
        )
        """
    )
    _enable_rls("form16_items")

    # ----- tax_reconciliation_matches -----
    op.create_table(
        "tax_reconciliation_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_table", sa.String(40), nullable=False),
        sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "canonical_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("match_kind", sa.String(40), nullable=True),
        sa.Column("matched_by", sa.String(20), nullable=False, server_default=sa.text("'auto'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "source_table",
            "source_row_id",
            "canonical_transaction_id",
            name="uq_tax_recon_matches_triplet",
        ),
    )
    op.create_index("ix_tax_recon_matches_user", "tax_reconciliation_matches", ["user_id"])
    _enable_rls("tax_reconciliation_matches")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
