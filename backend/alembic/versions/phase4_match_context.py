# ruff: noqa: E501
"""Phase 4 — enrich tax_reconciliation_matches with deductor/employer context.

Revision ID: phase4_match_context
Revises: phase35_tax_line_items
Create Date: 2026-05-21 09:00:00.000000

Adds four nullable columns to `tax_reconciliation_matches`:

  - match_signals (JSONB)       — structured snapshot of which signals fired
                                  (e.g. {"tan": true, "amount_gap": 0.5,
                                   "date_gap_days": 0, "employer_match": true})
  - source_deductor_tan         — denormalised so the API can surface "matched
                                  by TAN" without joining four tables.
  - source_deductor_pan         — same idea for AIS PAN matches.
  - source_employer_tan         — Form-16 employer TAN copy.

All columns are nullable; existing rows (none in production yet, but the
migration is safe regardless) get NULL. The new line-item reconciler in
Sprint 1.1 writes them on every fresh match.

`match_kind` stays String(40); the new values shipped by Sprint 1.1 ('tan_exact',
'amount_date_window', 'employer_amount', 'pan_amount', 'amount_only_fallback')
fit comfortably inside the existing column.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "phase4_match_context"
down_revision: Union[str, None] = "phase35_tax_line_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tax_reconciliation_matches",
        sa.Column("match_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tax_reconciliation_matches",
        sa.Column("source_deductor_tan", sa.String(20), nullable=True),
    )
    op.add_column(
        "tax_reconciliation_matches",
        sa.Column("source_deductor_pan", sa.String(20), nullable=True),
    )
    op.add_column(
        "tax_reconciliation_matches",
        sa.Column("source_employer_tan", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tax_reconciliation_matches", "source_employer_tan")
    op.drop_column("tax_reconciliation_matches", "source_deductor_pan")
    op.drop_column("tax_reconciliation_matches", "source_deductor_tan")
    op.drop_column("tax_reconciliation_matches", "match_signals")
