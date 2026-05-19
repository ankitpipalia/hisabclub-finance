"""Common types for ledger ↔ portal-document reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ReconciliationLine:
    """A single matched / unmatched pair.

    `kind`:
      - "matched"           — portal line matches a canonical ledger entry
      - "missing_in_ledger" — portal reports it; ledger does not have it
      - "missing_in_portal" — ledger has it; portal does not report it
      - "amount_mismatch"   — both sides exist; absolute gap > tolerance
    """

    kind: str
    label: str
    portal_amount: Decimal | None
    ledger_amount: Decimal | None
    delta: Decimal | None  # portal - ledger
    portal_date: date | None
    ledger_canonical_id: str | None
    notes: str


@dataclass(frozen=True)
class ReconciliationReport:
    fy: str
    source: str  # "AIS" | "26AS" | "Form-16" | ...
    matched: int
    missing_in_ledger: int
    missing_in_portal: int
    amount_mismatch: int
    total_portal_amount: Decimal
    total_ledger_amount: Decimal
    lines: tuple[ReconciliationLine, ...] = field(default_factory=tuple)
