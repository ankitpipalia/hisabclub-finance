"""allow review tasks without statement

Revision ID: phase3_review_nullable_statement
Revises: add_extraction_audit
Create Date: 2026-04-27 16:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase3_review_nullable_statement"
down_revision: Union[str, None] = "add_extraction_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "review_tasks",
        "statement_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM review_tasks
            WHERE statement_id IS NULL
            """
        )
    )
    op.alter_column(
        "review_tasks",
        "statement_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
