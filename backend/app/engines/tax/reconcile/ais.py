"""AIS (Annual Information Statement) ↔ ledger reconciliation.

AIS lists every financial transaction reported to the IT department:
salary, interest, dividend, mutual fund redemptions, securities purchases,
property sales, foreign remittances, GST returns, etc.

For a non-business salaried persona we currently bucket-reconcile the
high-value categories:

  - Salary               → match against ledger income credits
  - Interest from bank   → match against `interest_income` already aggregated
                            by tax_compliance
  - Dividend             → match against `dividend_income`
  - Securities sold      → flag for capital-gains workflow (not auto-matched)
  - Mutual fund sold     → flag for capital-gains workflow

This module is a thin aggregate-bucket reconciler; per-row matching is
covered by a future revision once the parser emits typed line-items.
"""

from __future__ import annotations

from decimal import Decimal

from app.engines.tax.reconcile.types import (
    ReconciliationLine,
    ReconciliationReport,
)

_DEFAULT_TOLERANCE = Decimal("100")


def reconcile_ais_buckets(
    *,
    fy: str,
    ais_salary: Decimal | None,
    ais_interest: Decimal | None,
    ais_dividend: Decimal | None,
    ais_securities_sold: Decimal | None,
    ledger_salary: Decimal,
    ledger_interest: Decimal,
    ledger_dividend: Decimal,
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> ReconciliationReport:
    """Bucket-level reconciliation; produces one line per category."""
    lines: list[ReconciliationLine] = []
    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    portal_total = (
        (ais_salary or Decimal("0"))
        + (ais_interest or Decimal("0"))
        + (ais_dividend or Decimal("0"))
        + (ais_securities_sold or Decimal("0"))
    )
    ledger_total = ledger_salary + ledger_interest + ledger_dividend

    def _bucket(
        label: str,
        portal: Decimal | None,
        ledger: Decimal,
        notes_mismatch: str,
        notes_missing_ledger: str,
        notes_missing_portal: str,
    ) -> None:
        nonlocal matched, missing_in_ledger, missing_in_portal, amount_mismatch
        portal_val = portal or Decimal("0")
        if portal_val == 0 and ledger == 0:
            return  # nothing to report
        if portal is None and ledger > 0:
            missing_in_portal += 1
            lines.append(
                ReconciliationLine(
                    kind="missing_in_portal",
                    label=f"{label}: ledger ₹{ledger}, not in AIS.",
                    portal_amount=None,
                    ledger_amount=ledger,
                    delta=None,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=notes_missing_portal,
                )
            )
            return
        if (portal_val > 0) and ledger == 0:
            missing_in_ledger += 1
            lines.append(
                ReconciliationLine(
                    kind="missing_in_ledger",
                    label=f"{label}: AIS ₹{portal_val}, no ledger entries.",
                    portal_amount=portal_val,
                    ledger_amount=Decimal("0"),
                    delta=portal_val,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=notes_missing_ledger,
                )
            )
            return
        delta = portal_val - ledger
        if abs(delta) <= tolerance:
            matched += 1
            lines.append(
                ReconciliationLine(
                    kind="matched",
                    label=f"{label}: AIS ₹{portal_val} ≈ ledger ₹{ledger}.",
                    portal_amount=portal_val,
                    ledger_amount=ledger,
                    delta=delta,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=f"Tolerance: ₹{tolerance}",
                )
            )
        else:
            amount_mismatch += 1
            direction = (
                "AIS reports MORE than ledger"
                if delta > 0
                else "Ledger has MORE than AIS"
            )
            lines.append(
                ReconciliationLine(
                    kind="amount_mismatch",
                    label=f"{label}: {direction} — gap ₹{abs(delta)}.",
                    portal_amount=portal_val,
                    ledger_amount=ledger,
                    delta=delta,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=notes_mismatch,
                )
            )

    _bucket(
        "Salary",
        ais_salary,
        ledger_salary,
        notes_mismatch=(
            "AIS aggregates salary as reported by your employer. "
            "Mismatch usually means bonus credited via another account, "
            "reimbursements, or missed credits."
        ),
        notes_missing_ledger="Salary statements may not be uploaded for the full FY.",
        notes_missing_portal=(
            "Salary in ledger but missing from AIS — your employer may not "
            "have filed TDS returns yet, or your PAN was not quoted correctly."
        ),
    )
    _bucket(
        "Interest from bank / FD",
        ais_interest,
        ledger_interest,
        notes_mismatch=(
            "Likely cause: TDS deduction at source reduced the bank credit, "
            "or interest from FD reinvested but accrued."
        ),
        notes_missing_ledger=(
            "Upload bank interest certificates for the FY, or check if some "
            "savings accounts are not yet ingested."
        ),
        notes_missing_portal=(
            "Interest in ledger but missing from AIS — small interest payouts "
            "(< ₹10,000) are not always reported to AIS."
        ),
    )
    _bucket(
        "Dividend",
        ais_dividend,
        ledger_dividend,
        notes_mismatch="Reconcile per company; DRP-paid dividends may delay.",
        notes_missing_ledger="Upload demat / broker statements for the FY.",
        notes_missing_portal=(
            "Dividend credited but not in AIS — the issuer may have a "
            "reporting lag, or your PAN was not linked to the demat."
        ),
    )

    if ais_securities_sold and ais_securities_sold > 0:
        # We don't have ledger CG amount; emit a flag rather than match.
        lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=(
                    f"Securities sold worth ₹{ais_securities_sold} in AIS — "
                    "capital gains workflow not yet automated."
                ),
                portal_amount=ais_securities_sold,
                ledger_amount=None,
                delta=None,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Upload broker P&L / capital gains statement so HisabClub "
                    "can compute STCG / LTCG with the right per-FY rates."
                ),
            )
        )

    return ReconciliationReport(
        fy=fy,
        source="AIS",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=portal_total,
        total_ledger_amount=ledger_total,
        lines=tuple(lines),
    )
