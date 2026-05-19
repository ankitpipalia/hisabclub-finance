"""26AS ↔ ledger TDS reconciliation.

Form 26AS aggregates TDS deducted on the user's PAN across all deductors:
employers (Part-A), interest payers (Part-A1), specified financial
transactions (Part-E), TCS (Part-B), and tax challans paid by the user
(Part-C).

For now we reconcile two flavours:
 1. TDS line items in 26AS Part-A / A1 against the user's expected income
    sources (sum of Form-16 TDS + interest-certificate TDS the user has
    uploaded).
 2. Self-paid challans in Part-C against the user's bank-statement debits to
    "INCOME TAX" or "ITD".

We deliberately keep the algorithm simple: bucket by deductor name + section
fingerprint (e.g. "192" for salary TDS) and compare totals. Per-row matching
is left to a future revision when the parser actually emits per-row data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from app.engines.tax.reconcile.types import (
    ReconciliationLine,
    ReconciliationReport,
)

_DEFAULT_TOLERANCE = Decimal("1")  # ₹1 tolerance for TDS aggregates


def reconcile_26as_tds(
    *,
    fy: str,
    portal_tds_total: Decimal | None,
    form16_tds_total: Decimal | None,
    interest_cert_tds_total: Decimal | None = None,
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> ReconciliationReport:
    """Compare 26AS TDS aggregate to known sources (Form-16 + interest certs)."""
    portal_total = portal_tds_total or Decimal("0")
    documented_total = (form16_tds_total or Decimal("0")) + (
        interest_cert_tds_total or Decimal("0")
    )

    lines: list[ReconciliationLine] = []
    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    if portal_tds_total is None and documented_total == 0:
        return ReconciliationReport(
            fy=fy,
            source="26AS",
            matched=0,
            missing_in_ledger=0,
            missing_in_portal=0,
            amount_mismatch=0,
            total_portal_amount=Decimal("0"),
            total_ledger_amount=Decimal("0"),
            lines=tuple(),
        )

    if portal_tds_total is None:
        missing_in_portal = 1
        lines.append(
            ReconciliationLine(
                kind="missing_in_portal",
                label=f"Form-16 / interest certificates reported ₹{documented_total} "
                f"TDS, but 26AS hasn't been uploaded for {fy}.",
                portal_amount=None,
                ledger_amount=documented_total,
                delta=None,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Download Form 26AS from the Income Tax e-Filing portal and upload it.",
            )
        )
        return ReconciliationReport(
            fy=fy,
            source="26AS",
            matched=matched,
            missing_in_ledger=missing_in_ledger,
            missing_in_portal=missing_in_portal,
            amount_mismatch=amount_mismatch,
            total_portal_amount=portal_total,
            total_ledger_amount=documented_total,
            lines=tuple(lines),
        )

    if documented_total == 0:
        missing_in_ledger = 1
        lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=f"26AS reports ₹{portal_total} TDS, but no Form-16 or "
                f"interest certificates have been uploaded for {fy}.",
                portal_amount=portal_total,
                ledger_amount=Decimal("0"),
                delta=portal_total,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Upload Form-16 (Part-A for TDS by employer) and any "
                    "Form-16A / interest certificates the deductor has issued."
                ),
            )
        )
        return ReconciliationReport(
            fy=fy,
            source="26AS",
            matched=matched,
            missing_in_ledger=missing_in_ledger,
            missing_in_portal=missing_in_portal,
            amount_mismatch=amount_mismatch,
            total_portal_amount=portal_total,
            total_ledger_amount=documented_total,
            lines=tuple(lines),
        )

    delta = portal_total - documented_total
    if abs(delta) <= tolerance:
        matched = 1
        lines.append(
            ReconciliationLine(
                kind="matched",
                label="26AS TDS aggregate matches Form-16 + interest certs within tolerance.",
                portal_amount=portal_total,
                ledger_amount=documented_total,
                delta=delta,
                portal_date=None,
                ledger_canonical_id=None,
                notes=f"Tolerance: ₹{tolerance}",
            )
        )
    else:
        amount_mismatch = 1
        direction = (
            "26AS reports MORE TDS than documented"
            if delta > 0
            else "Documented TDS is MORE than 26AS"
        )
        lines.append(
            ReconciliationLine(
                kind="amount_mismatch",
                label=f"{direction} — gap ₹{abs(delta)} "
                f"(26AS ₹{portal_total} vs documented ₹{documented_total}).",
                portal_amount=portal_total,
                ledger_amount=documented_total,
                delta=delta,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Possible causes: missing Form-16A from a bank/dividend "
                    "payer, employer reported TDS that did not reach 26AS, "
                    "or interest certificate not yet issued. Reconcile per "
                    "deductor TAN."
                ),
            )
        )

    return ReconciliationReport(
        fy=fy,
        source="26AS",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=portal_total,
        total_ledger_amount=documented_total,
        lines=tuple(lines),
    )


def reconcile_26as_self_paid_challans(
    *,
    fy: str,
    portal_self_paid_total: Decimal | None,
    ledger_tax_debits: Iterable[tuple[date, Decimal, str]],
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> ReconciliationReport:
    """Compare 26AS Part-C self-paid challans to bank-statement debits."""
    debits = list(ledger_tax_debits)
    ledger_total = sum((amt for _d, amt, _id in debits), start=Decimal("0"))
    portal_total = portal_self_paid_total or Decimal("0")

    lines: list[ReconciliationLine] = []
    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    if portal_total == 0 and ledger_total == 0:
        return ReconciliationReport(
            fy=fy,
            source="26AS-self-paid",
            matched=0,
            missing_in_ledger=0,
            missing_in_portal=0,
            amount_mismatch=0,
            total_portal_amount=Decimal("0"),
            total_ledger_amount=Decimal("0"),
            lines=tuple(),
        )

    delta = portal_total - ledger_total
    if abs(delta) <= tolerance:
        matched = 1
        lines.append(
            ReconciliationLine(
                kind="matched",
                label="26AS self-paid challans match bank tax debits.",
                portal_amount=portal_total,
                ledger_amount=ledger_total,
                delta=delta,
                portal_date=None,
                ledger_canonical_id=None,
                notes=f"Tolerance: ₹{tolerance}",
            )
        )
    elif portal_total > 0 and ledger_total == 0:
        missing_in_ledger = 1
        lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=f"26AS reports ₹{portal_total} self-paid tax, but no "
                "INCOME TAX debits found in the ledger.",
                portal_amount=portal_total,
                ledger_amount=Decimal("0"),
                delta=portal_total,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Upload the bank statement that contains the challan "
                    "debit, or correct merchant classification."
                ),
            )
        )
    elif ledger_total > 0 and portal_total == 0:
        missing_in_portal = 1
        lines.append(
            ReconciliationLine(
                kind="missing_in_portal",
                label=f"Ledger has ₹{ledger_total} INCOME TAX debits, but 26AS "
                "doesn't show a Part-C challan.",
                portal_amount=Decimal("0"),
                ledger_amount=ledger_total,
                delta=-ledger_total,
                portal_date=None,
                ledger_canonical_id=None,
                notes=(
                    "Possible causes: 26AS not refreshed (allow 3–5 days after "
                    "challan), challan failed to credit, or these debits are "
                    "for a different assessment year."
                ),
            )
        )
    else:
        amount_mismatch = 1
        direction = (
            "26AS reports MORE than ledger"
            if delta > 0
            else "Ledger has MORE than 26AS"
        )
        lines.append(
            ReconciliationLine(
                kind="amount_mismatch",
                label=f"{direction} — gap ₹{abs(delta)} "
                f"(26AS ₹{portal_total} vs ledger ₹{ledger_total}).",
                portal_amount=portal_total,
                ledger_amount=ledger_total,
                delta=delta,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Reconcile per challan/payment date.",
            )
        )

    return ReconciliationReport(
        fy=fy,
        source="26AS-self-paid",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=portal_total,
        total_ledger_amount=ledger_total,
        lines=tuple(lines),
    )
