"""add durable jobs and support tables

Revision ID: a9c4e2d1b7f0
Revises: f2b9d3c4a1e7
Create Date: 2026-03-30 06:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a9c4e2d1b7f0"
down_revision: Union[str, None] = "f2b9d3c4a1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extraction_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_pdf_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.String(length=40), nullable=False, server_default="parse_statement"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("current_stage", sa.String(length=40), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("dlq_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("dlq_reason", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["raw_pdf_id"], ["raw_pdfs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_id"], ["statements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_extraction_jobs_status_ready",
        "extraction_jobs",
        ["status", "next_run_at", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_jobs_user_created",
        "extraction_jobs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_jobs_raw_pdf",
        "extraction_jobs",
        ["raw_pdf_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "sync_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("cursor_key", sa.String(length=120), nullable=False),
        sa.Column("cursor_value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint(
        "uq_sync_cursors_user_provider_key",
        "sync_cursors",
        ["user_id", "provider", "cursor_key"],
    )

    op.create_table(
        "statement_period_coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bank_name", sa.String(length=50), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("account_number_masked", sa.String(length=50), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["statement_id"], ["statements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "bank_name",
            "account_type",
            "account_number_masked",
            "period_start",
            "period_end",
            name="uq_statement_coverage_user_account_period",
        ),
    )
    op.create_index(
        "ix_statement_coverage_user_period",
        "statement_period_coverage",
        ["user_id", "period_start", "period_end"],
        unique=False,
    )

    op.create_table(
        "institution_parser_support",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_code", sa.String(length=30), nullable=False),
        sa.Column("account_type", sa.String(length=30), nullable=False),
        sa.Column("parser_id", sa.String(length=120), nullable=True),
        sa.Column("parser_version", sa.String(length=60), nullable=True),
        sa.Column("is_supported", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expected_layout_signatures", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("observed_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bank_code", "account_type", name="uq_institution_parser_support"),
    )

    op.create_table(
        "institution_password_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_code", sa.String(length=30), nullable=False),
        sa.Column("account_scope", sa.String(length=20), nullable=False),
        sa.Column("pattern_type", sa.String(length=30), nullable=False),
        sa.Column("pattern_template", sa.String(length=255), nullable=False),
        sa.Column("variables_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "bank_code",
            "account_scope",
            name="uq_institution_password_pattern_scope",
        ),
    )
    op.create_index(
        "ix_institution_password_patterns_user_bank",
        "institution_password_patterns",
        ["user_id", "bank_code", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_institution_password_patterns_user_bank", table_name="institution_password_patterns")
    op.drop_table("institution_password_patterns")

    op.drop_table("institution_parser_support")

    op.drop_index("ix_statement_coverage_user_period", table_name="statement_period_coverage")
    op.drop_table("statement_period_coverage")

    op.drop_constraint("uq_sync_cursors_user_provider_key", "sync_cursors", type_="unique")
    op.drop_table("sync_cursors")

    op.drop_index("ix_extraction_jobs_raw_pdf", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_user_created", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_status_ready", table_name="extraction_jobs")
    op.drop_table("extraction_jobs")
