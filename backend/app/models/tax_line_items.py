"""Normalized tax-portal line-item tables (Sprint B.1).

Parsers emit one row per logical line of AIS / 26AS / Form-16. The reconcilers
in `engines/tax/reconcile/*.py` then attempt to match each row against
`canonical_transactions`, writing the result into `tax_reconciliation_matches`.

All four tables have RLS enabled (see migration `phase35_tax_line_items.py`)
and use the standard `app.request_user_id()` policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AisLineItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ais_line_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fy: Mapped[str] = mapped_column(String(10), nullable=False)
    # "salary" | "interest" | "dividend" | "securities_sold" | "tds" | ...
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(120))
    deductor_name: Mapped[str | None] = mapped_column(Text)
    deductor_pan: Mapped[str | None] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # AIS "Information Source" column (free-form bank/employer/intermediary).
    info_source: Mapped[str | None] = mapped_column(Text)
    # "open" | "matched" | "dismissed"
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    evidence_doc_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_artifacts.id", ondelete="SET NULL")
    )
    raw_row: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Form26AsLineItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "form26as_line_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fy: Mapped[str] = mapped_column(String(10), nullable=False)
    # "A" (TDS), "A1" (TDS-15G/H), "B" (TCS), "C" (advance/SAT challans)...
    part: Mapped[str] = mapped_column(String(8), nullable=False)
    deductor_tan: Mapped[str | None] = mapped_column(String(20))
    deductor_name: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(20))  # "192", "194A", ...
    amount_credit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount_tds: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    evidence_doc_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_artifacts.id", ondelete="SET NULL")
    )
    raw_row: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Form16Item(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "form16_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fy: Mapped[str] = mapped_column(String(10), nullable=False)
    employer_name: Mapped[str | None] = mapped_column(Text)
    employer_tan: Mapped[str | None] = mapped_column(String(20))
    # "gross_salary" | "tds" | "deduction_80c" | "perquisites" | "house_rent_allowance" | ...
    head: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    evidence_doc_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_artifacts.id", ondelete="SET NULL")
    )
    raw_row: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TaxReconciliationMatch(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tax_reconciliation_matches"
    __table_args__ = (
        UniqueConstraint(
            "source_table",
            "source_row_id",
            "canonical_transaction_id",
            name="uq_tax_recon_matches_triplet",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "ais_line_items" | "form26as_line_items" | "form16_items"
    source_table: Mapped[str] = mapped_column(String(40), nullable=False)
    source_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    match_kind: Mapped[str | None] = mapped_column(String(40))
    matched_by: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    # Phase 4 (Sprint 1.1): structured signal snapshot so the API can explain
    # *why* a match happened — {"tan": true, "amount_gap": 0.5, ...}.
    match_signals: Mapped[dict | None] = mapped_column(JSONB)
    # Denormalised columns so the dashboard can group matches by deductor or
    # employer without a four-way join.
    source_deductor_tan: Mapped[str | None] = mapped_column(String(20))
    source_deductor_pan: Mapped[str | None] = mapped_column(String(20))
    source_employer_tan: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
