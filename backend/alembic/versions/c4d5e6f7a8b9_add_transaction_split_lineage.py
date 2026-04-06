"""add transaction split lineage

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-07 00:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
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
        "transaction_splits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_canonical_txn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_canonical_txn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("split_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_canonical_txn_id"], ["canonical_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_canonical_txn_id"], ["canonical_transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("child_canonical_txn_id", name="uq_transaction_splits_child"),
        sa.UniqueConstraint("source_canonical_txn_id", "split_index", name="uq_transaction_splits_source_index"),
    )
    op.create_index(
        "ix_transaction_splits_user_source",
        "transaction_splits",
        ["user_id", "source_canonical_txn_id"],
        unique=False,
    )
    _enable_user_rls("transaction_splits")


def downgrade() -> None:
    _drop_user_rls("transaction_splits")
    op.drop_index("ix_transaction_splits_user_source", table_name="transaction_splits")
    op.drop_table("transaction_splits")
