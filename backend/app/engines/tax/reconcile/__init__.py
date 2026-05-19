"""Ledger reconciliation engines for tax-portal documents (AIS / 26AS / Form-16).

Each module exposes a `reconcile_*` async function that takes a user_id +
financial_year and returns a `ReconciliationReport` listing matched and
unmatched line items.

These engines DO NOT modify canonical_transactions — they emit findings that
the API surfaces as review tasks for the user to action.
"""

from app.engines.tax.reconcile.types import (
    ReconciliationLine,
    ReconciliationReport,
)

__all__ = ["ReconciliationLine", "ReconciliationReport"]
