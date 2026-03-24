"""add document artifacts and transaction nature

Revision ID: 9f3d1b2c7a01
Revises: 15c31c4bdeba
Create Date: 2026-03-24 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9f3d1b2c7a01"
down_revision: Union[str, None] = "15c31c4bdeba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "canonical_transactions",
        sa.Column(
            "transaction_nature",
            sa.String(length=30),
            server_default="expense",
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE canonical_transactions
        SET transaction_nature = CASE
            WHEN direction = 'credit' THEN 'income'
            ELSE 'expense'
        END
        """
    )

    op.create_table(
        "document_artifacts",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("file_ext", sa.String(length=20), nullable=False),
        sa.Column("file_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("doc_subtype", sa.String(length=50), nullable=True),
        sa.Column("bank_hint", sa.String(length=50), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="discovered",
            nullable=False,
        ),
        sa.Column("parse_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "file_hash_sha256", name="uq_doc_artifacts_user_hash"),
    )
    op.create_index(
        "ix_doc_artifacts_user_status",
        "document_artifacts",
        ["user_id", "status"],
        unique=False,
    )

    op.alter_column("canonical_transactions", "transaction_nature", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_doc_artifacts_user_status", table_name="document_artifacts")
    op.drop_table("document_artifacts")
    op.drop_column("canonical_transactions", "transaction_nature")

