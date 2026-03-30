"""add phase2 quality controls and review tasks

Revision ID: f9a0b1c2d3e4
Revises: e1f2a3b4c5d6
Create Date: 2026-03-30 11:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "raw_pdfs",
        sa.Column("storage_tier", sa.String(length=20), nullable=False, server_default="hot"),
    )
    op.add_column("raw_pdfs", sa.Column("cold_storage_path", sa.Text(), nullable=True))

    op.add_column(
        "parsed_transactions",
        sa.Column("is_quarantined", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "parsed_transactions",
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "parsed_transactions",
        sa.Column("override_reason_code", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "parsed_transactions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_parsed_transactions_reviewer_user_id",
        "parsed_transactions",
        "users",
        ["reviewer_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_parsed_transactions_statement_quarantined",
        "parsed_transactions",
        ["statement_id", "is_quarantined"],
        unique=False,
    )

    op.add_column("statements", sa.Column("expected_row_count", sa.Integer(), nullable=True))
    op.add_column("statements", sa.Column("extracted_row_count", sa.Integer(), nullable=True))
    op.add_column("statements", sa.Column("promoted_row_count", sa.Integer(), nullable=True))
    op.add_column("statements", sa.Column("quarantined_row_count", sa.Integer(), nullable=True))
    op.add_column("statements", sa.Column("yield_rate", sa.Float(), nullable=True))

    op.add_column(
        "institution_parser_support",
        sa.Column("observed_expected_rows", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "institution_parser_support",
        sa.Column("observed_extracted_rows", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "review_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False, server_default="statement_review"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("reason_code", sa.String(length=60), nullable=False, server_default="low_confidence"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["statement_id"], ["statements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('open','resolved','dismissed')", name="ck_review_tasks_status"),
    )
    op.create_index(
        "ix_review_tasks_user_status_created",
        "review_tasks",
        ["user_id", "status", "created_at"],
        unique=False,
    )
    op.execute("ALTER TABLE review_tasks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_tasks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY review_tasks_tenant_isolation ON review_tasks
        USING (app.is_worker_context() OR user_id = app.request_user_id())
        WITH CHECK (app.is_worker_context() OR user_id = app.request_user_id())
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON review_tasks TO hisabclub_rls")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS review_tasks_tenant_isolation ON review_tasks")
    op.drop_index("ix_review_tasks_user_status_created", table_name="review_tasks")
    op.drop_table("review_tasks")

    op.drop_column("institution_parser_support", "observed_extracted_rows")
    op.drop_column("institution_parser_support", "observed_expected_rows")

    op.drop_column("statements", "yield_rate")
    op.drop_column("statements", "quarantined_row_count")
    op.drop_column("statements", "promoted_row_count")
    op.drop_column("statements", "extracted_row_count")
    op.drop_column("statements", "expected_row_count")

    op.drop_index("ix_parsed_transactions_statement_quarantined", table_name="parsed_transactions")
    op.drop_constraint(
        "fk_parsed_transactions_reviewer_user_id",
        "parsed_transactions",
        type_="foreignkey",
    )
    op.drop_column("parsed_transactions", "reviewed_at")
    op.drop_column("parsed_transactions", "override_reason_code")
    op.drop_column("parsed_transactions", "reviewer_user_id")
    op.drop_column("parsed_transactions", "is_quarantined")

    op.drop_column("raw_pdfs", "cold_storage_path")
    op.drop_column("raw_pdfs", "storage_tier")
