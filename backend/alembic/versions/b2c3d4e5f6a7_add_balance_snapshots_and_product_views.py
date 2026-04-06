"""add balance snapshots and product views

Revision ID: b2c3d4e5f6a7
Revises: a4b5c6d7e8f9
Create Date: 2026-04-06 22:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enable_user_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_isolation ON {table_name}
        USING (app.is_worker_context() OR user_id = app.request_user_id())
        WITH CHECK (app.is_worker_context() OR user_id = app.request_user_id())
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO hisabclub_rls")


def _drop_user_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")


def upgrade() -> None:
    op.create_table(
        "balance_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position_key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("entry_kind", sa.String(length=20), nullable=False, server_default="asset"),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("institution_name", sa.String(length=100), nullable=True),
        sa.Column("account_masked", sa.String(length=50), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["statement_id"], ["statements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("statement_id", name="uq_balance_snapshots_statement_id"),
        sa.CheckConstraint("source_kind IN ('manual','statement')", name="ck_balance_snapshots_source_kind"),
        sa.CheckConstraint("entry_kind IN ('asset','liability')", name="ck_balance_snapshots_entry_kind"),
    )
    op.create_index(
        "ix_balance_snapshots_user_position_date",
        "balance_snapshots",
        ["user_id", "position_key", "as_of_date"],
        unique=False,
    )
    op.create_index(
        "ix_balance_snapshots_user_source_created",
        "balance_snapshots",
        ["user_id", "source_kind", "created_at"],
        unique=False,
    )
    _enable_user_rls("balance_snapshots")


def downgrade() -> None:
    _drop_user_rls("balance_snapshots")
    op.drop_index("ix_balance_snapshots_user_source_created", table_name="balance_snapshots")
    op.drop_index("ix_balance_snapshots_user_position_date", table_name="balance_snapshots")
    op.drop_table("balance_snapshots")
