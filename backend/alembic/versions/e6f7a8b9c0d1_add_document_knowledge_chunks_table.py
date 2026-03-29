"""add document knowledge chunks table

Revision ID: e6f7a8b9c0d1
Revises: c3d9e1a2b7f4
Create Date: 2026-03-30 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "c3d9e1a2b7f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_knowledge_chunks",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_pdf_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("source_filename", sa.String(length=500), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=True),
        sa.Column("bank_hint", sa.String(length=50), nullable=True),
        sa.Column("account_type_hint", sa.String(length=50), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("chunk_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["document_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_pdf_id"], ["raw_pdfs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_knowledge_chunks_user_id"),
        "document_knowledge_chunks",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_knowledge_chunks_raw_pdf_id"),
        "document_knowledge_chunks",
        ["raw_pdf_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_knowledge_chunks_artifact_id"),
        "document_knowledge_chunks",
        ["artifact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_knowledge_chunks_bank_hint"),
        "document_knowledge_chunks",
        ["bank_hint"],
        unique=False,
    )
    op.create_index(
        "ix_document_knowledge_chunks_user_created_at",
        "document_knowledge_chunks",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_knowledge_chunks_user_created_at", table_name="document_knowledge_chunks")
    op.drop_index(op.f("ix_document_knowledge_chunks_bank_hint"), table_name="document_knowledge_chunks")
    op.drop_index(op.f("ix_document_knowledge_chunks_artifact_id"), table_name="document_knowledge_chunks")
    op.drop_index(op.f("ix_document_knowledge_chunks_raw_pdf_id"), table_name="document_knowledge_chunks")
    op.drop_index(op.f("ix_document_knowledge_chunks_user_id"), table_name="document_knowledge_chunks")
    op.drop_table("document_knowledge_chunks")
