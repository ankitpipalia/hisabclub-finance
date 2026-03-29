"""add fingerprints transfer matches and parse status checks

Revision ID: f2b9d3c4a1e7
Revises: e6f7a8b9c0d1
Create Date: 2026-03-30 05:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f2b9d3c4a1e7"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("raw_pdfs", sa.Column("semantic_fingerprint", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_raw_pdfs_user_semantic_fingerprint",
        "raw_pdfs",
        ["user_id", "semantic_fingerprint"],
        unique=False,
    )

    op.add_column(
        "parsed_transactions",
        sa.Column("dedupe_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_parsed_transactions_user_dedupe_fingerprint",
        "parsed_transactions",
        ["user_id", "dedupe_fingerprint"],
        unique=False,
    )

    op.add_column(
        "canonical_transactions",
        sa.Column("dedupe_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_canonical_transactions_user_dedupe_fingerprint",
        "canonical_transactions",
        ["user_id", "dedupe_fingerprint"],
        unique=False,
    )

    op.execute(
        """
        UPDATE statements
        SET parse_status = CASE
          WHEN parse_status IN ('success', 'parsed') THEN 'parsed'
          WHEN parse_status IN ('no_transactions', 'review_required') THEN 'partial'
          WHEN parse_status IN ('pending', 'parsing', 'uploaded', 'classifying', 'extracting', 'validating', 'partial', 'failed')
            THEN parse_status
          ELSE 'failed'
        END
        """
    )
    op.alter_column(
        "statements",
        "parse_status",
        existing_type=sa.String(length=20),
        server_default="uploaded",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_statements_parse_status",
        "statements",
        "parse_status IN ('uploaded','classifying','extracting','validating','review_required','parsed','partial','failed')",
    )
    op.add_column("statements", sa.Column("statement_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("statements", sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("statements", sa.Column("supersedes_statement_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("statements", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.create_foreign_key(
        "fk_statements_supersedes_statement_id",
        "statements",
        "statements",
        ["supersedes_statement_id"],
        ["id"],
    )
    op.create_index(
        "ix_statements_user_active_created",
        "statements",
        ["user_id", "is_active", "created_at"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_statements_active_fingerprint
        ON statements (user_id, statement_fingerprint)
        WHERE is_active = true AND statement_fingerprint IS NOT NULL
        """
    )

    op.create_table(
        "transfer_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("debit_canonical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_canonical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_type", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("resolution_status", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["debit_canonical_id"], ["canonical_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credit_canonical_id"], ["canonical_transactions.id"], ondelete="CASCADE"),
        sa.CheckConstraint("debit_canonical_id <> credit_canonical_id", name="ck_transfer_matches_distinct_legs"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_transfer_matches_confidence"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transfer_matches_user_status",
        "transfer_matches",
        ["user_id", "resolution_status", "matched_at"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_transfer_matches_debit_credit",
        "transfer_matches",
        ["debit_canonical_id", "credit_canonical_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_transfer_matches_debit_credit", "transfer_matches", type_="unique")
    op.drop_index("ix_transfer_matches_user_status", table_name="transfer_matches")
    op.drop_table("transfer_matches")

    op.drop_constraint("ck_statements_parse_status", "statements", type_="check")
    op.execute("DROP INDEX IF EXISTS uq_statements_active_fingerprint")
    op.drop_index("ix_statements_user_active_created", table_name="statements")
    op.drop_constraint("fk_statements_supersedes_statement_id", "statements", type_="foreignkey")
    op.drop_column("statements", "is_active")
    op.drop_column("statements", "supersedes_statement_id")
    op.drop_column("statements", "version_no")
    op.drop_column("statements", "statement_fingerprint")
    op.alter_column(
        "statements",
        "parse_status",
        existing_type=sa.String(length=20),
        server_default="pending",
        existing_nullable=False,
    )

    op.drop_index(
        "ix_canonical_transactions_user_dedupe_fingerprint",
        table_name="canonical_transactions",
    )
    op.drop_column("canonical_transactions", "dedupe_fingerprint")

    op.drop_index(
        "ix_parsed_transactions_user_dedupe_fingerprint",
        table_name="parsed_transactions",
    )
    op.drop_column("parsed_transactions", "dedupe_fingerprint")

    op.drop_index("ix_raw_pdfs_user_semantic_fingerprint", table_name="raw_pdfs")
    op.drop_column("raw_pdfs", "semantic_fingerprint")
