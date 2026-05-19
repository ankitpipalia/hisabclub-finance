"""Form-16 ↔ ledger salary credit reconciliation.

The user uploads a Form-16 (Part-A + Part-B); the parser extracts:
 - gross_salary
 - deductions claimed
 - tds_total
 - employer_name (best-effort, may be None)

This module compares:
 - Form-16 `gross_salary` (annual) against the sum of credits in
   `canonical_transactions` for the user, FY-windowed, where
   `transaction_nature='income'` (or merchant resembles a salary credit).
 - Form-16 `tds_total` against the user's tax_portal_data (if 26AS is also
   uploaded the cross-check is run there).

This is a *plain-Decimal* function — it does no DB I/O. The caller (API
endpoint) is responsible for assembling the inputs.

Returns a `ReconciliationReport`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from app.engines.tax.reconcile.types import (
    ReconciliationLine,
    ReconciliationReport,
)

_DEFAULT_TOLERANCE = Decimal("100")  # ₹100 tolerance for salary credits


def reconcile_form16(
    *,
    fy: str,
    form16_gross_salary: Decimal | None,
    ledger_salary_credits: Iterable[tuple[date, Decimal, str]],
    employer_name_hint: str | None = None,
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> ReconciliationReport:
    """Reconcile Form-16 gross salary vs ledger income credits.

    `ledger_salary_credits` is an iterable of `(txn_date, amount, canonical_id)`
    for transactions marked as income from the employer (caller filters).
    """
    credits = list(ledger_salary_credits)
    ledger_total = sum((amt for _d, amt, _id in credits), start=Decimal("0"))
    portal_total = form16_gross_salary or Decimal("0")

    lines: list[ReconciliationLine] = []

    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    if form16_gross_salary is None and not credits:
        # Both empty — nothing to reconcile.
        return ReconciliationReport(
            fy=fy,
            source="Form-16",
            matched=0,
            missing_in_ledger=0,
            missing_in_portal=0,
            amount_mismatch=0,
            total_portal_amount=Decimal("0"),
            total_ledger_amount=Decimal("0"),
            lines=tuple(),
        )

    if form16_gross_salary is None:
        # User has salary credits in the ledger but didn't upload Form-16.
        missing_in_portal = 1
        lines.append(
            ReconciliationLine(
                kind="missing_in_portal",
                label=f"Salary credits worth ₹{ledger_total} found, "
                f"no Form-16 uploaded for {fy}.",
                portal_amount=None,
                ledger_amount=ledger_total,
                delta=None,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Upload Form-16 (Part-A + Part-B) so HisabClub can "
                    "match TDS, gross salary, and Sec 80x deductions."
                ),
            )
        )
        return ReconciliationReport(
            fy=fy,
            source="Form-16",
            matched=matched,
            missing_in_ledger=missing_in_ledger,
            missing_in_portal=missing_in_portal,
            amount_mismatch=amount_mismatch,
            total_portal_amount=portal_total,
            total_ledger_amount=ledger_total,
            lines=tuple(lines),
        )

    if not credits:
        # Form-16 says salary but ledger sees no credits — bank statement
        # missing or merchant misclassified.
        missing_in_ledger = 1
        lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=f"Form-16 reports ₹{form16_gross_salary} gross salary, "
                f"but no income credits found in the ledger for {fy}.",
                portal_amount=form16_gross_salary,
                ledger_amount=Decimal("0"),
                delta=form16_gross_salary,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Likely cause: salary statements not yet uploaded, OR "
                    f"merchant {employer_name_hint or '<employer>'} not "
                    "classified as income. Upload the relevant bank statement "
                    "or correct the merchant rule."
                ),
            )
        )
        return ReconciliationReport(
            fy=fy,
            source="Form-16",
            matched=matched,
            missing_in_ledger=missing_in_ledger,
            missing_in_portal=missing_in_portal,
            amount_mismatch=amount_mismatch,
            total_portal_amount=portal_total,
            total_ledger_amount=ledger_total,
            lines=tuple(lines),
        )

    delta = portal_total - ledger_total
    if abs(delta) <= tolerance:
        matched = 1
        lines.append(
            ReconciliationLine(
                kind="matched",
                label="Form-16 gross salary matches ledger income credits within tolerance.",
                portal_amount=portal_total,
                ledger_amount=ledger_total,
                delta=delta,
                portal_date=None,
                ledger_canonical_id=None,
                notes=f"Tolerance: ₹{tolerance}",
            )
        )
    else:
        amount_mismatch = 1
        direction = (
            "Form-16 reports MORE than ledger"
            if delta > 0
            else "Ledger has MORE than Form-16"
        )
        lines.append(
            ReconciliationLine(
                kind="amount_mismatch",
                label=f"{direction} — gap ₹{abs(delta)} "
                f"(Form-16 ₹{portal_total} vs ledger ₹{ledger_total}).",
                portal_amount=portal_total,
                ledger_amount=ledger_total,
                delta=delta,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Possible causes: bonus paid via different account, "
                    "reimbursements, missed credit, or merchant misclassified."
                ),
            )
        )

    return ReconciliationReport(
        fy=fy,
        source="Form-16",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=portal_total,
        total_ledger_amount=ledger_total,
        lines=tuple(lines),
    )
