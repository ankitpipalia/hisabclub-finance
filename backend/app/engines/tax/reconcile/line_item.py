"""Line-item reconcilers (Sprint B.3).

Walk every row in `ais_line_items` / `form26as_line_items` / `form16_items`
for the user+FY and try to match against `canonical_transactions`. Matches
become rows in `tax_reconciliation_matches`. Unmatched lines + un-cited
canonical entries become `ReconciliationLine` records the API surfaces.

This complements the aggregate reconcilers in `wire.py` — when line tables
are populated, the line-item reconciler runs FIRST and the aggregate
reconciler only kicks in when no lines were inserted (e.g. parser
returned a degenerate `lines: []`).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.tax.reconcile.types import (
    ReconciliationLine,
    ReconciliationReport,
)
from app.models.canonical_transaction import CanonicalTransaction
from app.models.tax_line_items import (
    AisLineItem,
    Form16Item,
    Form26AsLineItem,
    TaxReconciliationMatch,
)

# Default tolerance for amount matching. AIS / Form-16 often rounds to nearest ₹.
_DEFAULT_AMOUNT_TOLERANCE = Decimal("100")
# 5% tolerance applies to large amounts (salary ₹15L vs Form-16 ₹15.04L is fine).
_PROPORTIONAL_TOLERANCE = Decimal("0.05")


def _within_tolerance(portal: Decimal, ledger: Decimal) -> bool:
    if portal == 0 or ledger == 0:
        return False
    diff = abs(portal - ledger)
    if diff <= _DEFAULT_AMOUNT_TOLERANCE:
        return True
    larger = max(portal, ledger)
    return diff / larger <= _PROPORTIONAL_TOLERANCE


def _fy_window(fy: str) -> tuple[date, date]:
    """Parse an FY code into (start, end). Centralises the lenient parsing
    rules used by the aggregate reconciler."""
    from app.engines.tax.reconcile.wire import _fy_window as _impl

    return _impl(fy)


async def _candidate_canonicals_for_income(
    db: AsyncSession,
    user_id: uuid.UUID,
    fy: str,
    nature_in: tuple[str, ...],
) -> list[CanonicalTransaction]:
    start, end = _fy_window(fy)
    stmt = select(CanonicalTransaction).where(
        CanonicalTransaction.user_id == user_id,
        CanonicalTransaction.transaction_date >= start,
        CanonicalTransaction.transaction_date <= end,
        CanonicalTransaction.is_excluded == False,  # noqa: E712
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        row
        for row in rows
        if (row.transaction_nature or "").lower() in nature_in
    ]


async def _ais_unmatched_lines(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> list[AisLineItem]:
    rows = (
        await db.execute(
            select(AisLineItem).where(
                AisLineItem.user_id == user_id,
                AisLineItem.fy == fy,
                AisLineItem.status == "open",
            )
        )
    ).scalars().all()
    return list(rows)


async def _existing_match_canonical_id(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_table: str,
    source_row_id: uuid.UUID,
) -> uuid.UUID | None:
    row = (
        await db.execute(
            select(TaxReconciliationMatch.canonical_transaction_id).where(
                TaxReconciliationMatch.user_id == user_id,
                TaxReconciliationMatch.source_table == source_table,
                TaxReconciliationMatch.source_row_id == source_row_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    return row


def _bucket_category(canonical: CanonicalTransaction) -> str | None:
    """Map a canonical row to the AIS category it should match against."""
    nature = (canonical.transaction_nature or "").lower()
    merchant = (canonical.merchant_raw or "").upper()
    if nature == "interest_income":
        return "interest"
    if nature == "dividend_income":
        return "dividend"
    if nature == "income" and ("SALARY" in merchant or "PAYROLL" in merchant):
        return "salary"
    return None


async def reconcile_ais_line_items(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> ReconciliationReport:
    """Per-line AIS reconciliation. Each `ais_line_items` row is either
    matched to a canonical transaction (writing a `tax_reconciliation_matches`
    row), or flagged as missing-in-ledger. Canonical transactions in the
    salary/interest/dividend buckets that have no matching AIS line are
    flagged as missing-in-portal.
    """
    lines = await _ais_unmatched_lines(db, user_id, fy)
    canonicals = await _candidate_canonicals_for_income(
        db,
        user_id,
        fy,
        nature_in=("income", "interest_income", "dividend_income"),
    )
    {row.id: row for row in canonicals}
    matched_canonical_ids: set[uuid.UUID] = set()

    report_lines: list[ReconciliationLine] = []
    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    for line in lines:
        existing_match_id = await _existing_match_canonical_id(
            db,
            user_id=user_id,
            source_table="ais_line_items",
            source_row_id=line.id,
        )
        if existing_match_id is not None:
            matched_canonical_ids.add(existing_match_id)
            matched += 1
            continue

        candidates = [
            c for c in canonicals
            if _bucket_category(c) == line.category
            and c.id not in matched_canonical_ids
        ]
        if line.category == "securities_sold":
            # Capital gains aren't auto-matched; route to review.
            report_lines.append(
                ReconciliationLine(
                    kind="missing_in_ledger",
                    label=(
                        f"AIS securities sold: ₹{line.amount} "
                        f"({line.info_source or 'unknown source'}) — "
                        "upload broker P&L to reconcile."
                    ),
                    portal_amount=line.amount,
                    ledger_amount=None,
                    delta=None,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=(
                        "Capital gains require broker P&L for STCG/LTCG split. "
                        "HisabClub doesn't auto-match these yet."
                    ),
                )
            )
            missing_in_ledger += 1
            continue

        best: tuple[Decimal, CanonicalTransaction] | None = None
        for cand in candidates:
            cand_amt = Decimal(str(cand.amount))
            if _within_tolerance(line.amount, cand_amt):
                gap = abs(line.amount - cand_amt)
                if best is None or gap < best[0]:
                    best = (gap, cand)

        if best is not None:
            gap, cand = best
            db.add(
                TaxReconciliationMatch(
                    user_id=user_id,
                    source_table="ais_line_items",
                    source_row_id=line.id,
                    canonical_transaction_id=cand.id,
                    match_score=_score(gap, line.amount),
                    match_kind="amount_window",
                    matched_by="auto",
                )
            )
            matched_canonical_ids.add(cand.id)
            line.status = "matched"
            matched += 1
            report_lines.append(
                ReconciliationLine(
                    kind="matched",
                    label=(
                        f"{line.category.title()} ₹{line.amount} ≈ ledger "
                        f"₹{Decimal(str(cand.amount))} ({cand.merchant_raw})"
                    ),
                    portal_amount=line.amount,
                    ledger_amount=Decimal(str(cand.amount)),
                    delta=line.amount - Decimal(str(cand.amount)),
                    portal_date=None,
                    ledger_canonical_id=str(cand.id),
                    notes=f"Tolerance: ₹{_DEFAULT_AMOUNT_TOLERANCE}",
                )
            )
        else:
            missing_in_ledger += 1
            report_lines.append(
                ReconciliationLine(
                    kind="missing_in_ledger",
                    label=(
                        f"AIS {line.category}: ₹{line.amount} "
                        f"({line.info_source or 'unknown source'}) — no matching ledger row"
                    ),
                    portal_amount=line.amount,
                    ledger_amount=None,
                    delta=None,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=(
                        "Upload the corresponding bank/employer statement "
                        "or correct merchant classification."
                    ),
                )
            )

    # Anything in the salary/interest/dividend bucket that DIDN'T receive a
    # match is "missing in portal" (ledger has it, AIS doesn't).
    for cand in canonicals:
        if cand.id in matched_canonical_ids:
            continue
        bucket = _bucket_category(cand)
        if bucket is None:
            continue
        # Skip very small interest credits that AIS routinely omits.
        amt = Decimal(str(cand.amount))
        if bucket == "interest" and amt < Decimal("100"):
            continue
        missing_in_portal += 1
        report_lines.append(
            ReconciliationLine(
                kind="missing_in_portal",
                label=(
                    f"Ledger {bucket} ₹{amt} ({cand.merchant_raw}) "
                    "not found in AIS"
                ),
                portal_amount=None,
                ledger_amount=amt,
                delta=None,
                portal_date=None,
                ledger_canonical_id=str(cand.id),
                notes=(
                    "Possible causes: small payouts < ₹10k are not always in AIS, "
                    "PAN-mismatch on source, or reporting lag."
                ),
            )
        )

    portal_total = sum((line.amount for line in lines), Decimal("0"))
    ledger_total = sum((Decimal(str(c.amount)) for c in canonicals), Decimal("0"))

    return ReconciliationReport(
        fy=fy,
        source="AIS",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=portal_total,
        total_ledger_amount=ledger_total,
        lines=tuple(report_lines),
    )


def _score(gap: Decimal, total: Decimal) -> Decimal:
    """Compute a 0..1 match score; closer = higher."""
    if total == 0:
        return Decimal("0.500")
    quality = max(Decimal("0"), Decimal("1") - (gap / total))
    return quality.quantize(Decimal("0.001"))


async def reconcile_form16_line_items(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> ReconciliationReport:
    """Match Form-16 `gross_salary` head against the sum of ledger salary
    credits for the FY. Other heads (TDS, deductions) are surfaced as
    informational lines."""
    f16_rows = (
        await db.execute(
            select(Form16Item).where(
                Form16Item.user_id == user_id,
                Form16Item.fy == fy,
            )
        )
    ).scalars().all()

    if not f16_rows:
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

    salary_lines = [r for r in f16_rows if r.head == "gross_salary"]
    tds_lines = [r for r in f16_rows if r.head == "tds"]

    canonicals = await _candidate_canonicals_for_income(
        db, user_id, fy, nature_in=("income",)
    )
    salary_credits = [
        c for c in canonicals
        if "SALARY" in (c.merchant_raw or "").upper()
        or "PAYROLL" in (c.merchant_raw or "").upper()
    ]
    salary_total_ledger = sum(
        (Decimal(str(c.amount)) for c in salary_credits), Decimal("0")
    )
    salary_total_portal = sum((r.amount for r in salary_lines), Decimal("0"))

    report_lines: list[ReconciliationLine] = []
    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    if salary_total_portal > 0 and salary_credits:
        if _within_tolerance(salary_total_portal, salary_total_ledger):
            matched = 1
            for sal_line in salary_lines:
                if await _existing_match_canonical_id(
                    db,
                    user_id=user_id,
                    source_table="form16_items",
                    source_row_id=sal_line.id,
                ) is not None:
                    continue
                # Best-effort: match against the largest single credit.
                largest = max(salary_credits, key=lambda c: Decimal(str(c.amount)))
                db.add(
                    TaxReconciliationMatch(
                        user_id=user_id,
                        source_table="form16_items",
                        source_row_id=sal_line.id,
                        canonical_transaction_id=largest.id,
                        match_score=_score(
                            abs(sal_line.amount - salary_total_ledger),
                            sal_line.amount,
                        ),
                        match_kind="annual_aggregate",
                        matched_by="auto",
                    )
                )
                sal_line  # noqa: B018 — referenced for clarity
            report_lines.append(
                ReconciliationLine(
                    kind="matched",
                    label=(
                        f"Form-16 gross salary ₹{salary_total_portal} ≈ "
                        f"ledger income credits ₹{salary_total_ledger}"
                    ),
                    portal_amount=salary_total_portal,
                    ledger_amount=salary_total_ledger,
                    delta=salary_total_portal - salary_total_ledger,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=f"Tolerance: ₹{_DEFAULT_AMOUNT_TOLERANCE} or 5%",
                )
            )
        else:
            amount_mismatch = 1
            report_lines.append(
                ReconciliationLine(
                    kind="amount_mismatch",
                    label=(
                        f"Form-16 gross ₹{salary_total_portal} vs ledger "
                        f"income credits ₹{salary_total_ledger}"
                    ),
                    portal_amount=salary_total_portal,
                    ledger_amount=salary_total_ledger,
                    delta=salary_total_portal - salary_total_ledger,
                    portal_date=None,
                    ledger_canonical_id=None,
                    notes=(
                        "Possible causes: bonus credited via different account, "
                        "reimbursements, missed credit, or merchant misclassified."
                    ),
                )
            )
    elif salary_total_portal > 0:
        missing_in_ledger = 1
        report_lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=f"Form-16 reports ₹{salary_total_portal} salary, ledger has none.",
                portal_amount=salary_total_portal,
                ledger_amount=Decimal("0"),
                delta=salary_total_portal,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Upload the bank statement that received the salary credits.",
            )
        )

    # TDS lines are surfaced as informational entries (they get cross-checked
    # against 26AS, not the ledger directly).
    for tds_line in tds_lines:
        report_lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=f"Form-16 TDS ₹{tds_line.amount} — cross-check against 26AS Part-A.",
                portal_amount=tds_line.amount,
                ledger_amount=None,
                delta=None,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Upload Form 26AS to reconcile TDS aggregate.",
            )
        )

    return ReconciliationReport(
        fy=fy,
        source="Form-16",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=salary_total_portal,
        total_ledger_amount=salary_total_ledger,
        lines=tuple(report_lines),
    )


async def reconcile_form26as_line_items(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> ReconciliationReport:
    """Sum TDS across Part-A rows and compare to documented TDS from Form-16."""
    f26_rows = (
        await db.execute(
            select(Form26AsLineItem).where(
                Form26AsLineItem.user_id == user_id,
                Form26AsLineItem.fy == fy,
            )
        )
    ).scalars().all()
    f16_tds_rows = (
        await db.execute(
            select(Form16Item).where(
                Form16Item.user_id == user_id,
                Form16Item.fy == fy,
                Form16Item.head == "tds",
            )
        )
    ).scalars().all()

    portal_tds = sum(
        (r.amount_tds or Decimal("0") for r in f26_rows if r.part in {"A", "A1"}),
        Decimal("0"),
    )
    documented_tds = sum((r.amount for r in f16_tds_rows), Decimal("0"))

    report_lines: list[ReconciliationLine] = []
    matched = 0
    missing_in_ledger = 0
    missing_in_portal = 0
    amount_mismatch = 0

    if portal_tds == 0 and documented_tds == 0:
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

    if abs(portal_tds - documented_tds) <= Decimal("1") and portal_tds > 0:
        matched = 1
        report_lines.append(
            ReconciliationLine(
                kind="matched",
                label=f"26AS Part-A TDS ₹{portal_tds} ≈ Form-16 ₹{documented_tds}",
                portal_amount=portal_tds,
                ledger_amount=documented_tds,
                delta=portal_tds - documented_tds,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Tolerance: ₹1",
            )
        )
    elif portal_tds > 0 and documented_tds == 0:
        missing_in_ledger = 1
        report_lines.append(
            ReconciliationLine(
                kind="missing_in_ledger",
                label=f"26AS reports ₹{portal_tds} TDS, no Form-16 uploaded.",
                portal_amount=portal_tds,
                ledger_amount=Decimal("0"),
                delta=portal_tds,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Upload Form-16 to reconcile.",
            )
        )
    elif documented_tds > 0 and portal_tds == 0:
        missing_in_portal = 1
        report_lines.append(
            ReconciliationLine(
                kind="missing_in_portal",
                label=f"Form-16 reports ₹{documented_tds} TDS, no 26AS uploaded.",
                portal_amount=Decimal("0"),
                ledger_amount=documented_tds,
                delta=-documented_tds,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Download 26AS from the e-Filing portal and upload it.",
            )
        )
    else:
        amount_mismatch = 1
        report_lines.append(
            ReconciliationLine(
                kind="amount_mismatch",
                label=(
                    f"26AS TDS ₹{portal_tds} vs Form-16 ₹{documented_tds} "
                    f"— gap ₹{abs(portal_tds - documented_tds)}"
                ),
                portal_amount=portal_tds,
                ledger_amount=documented_tds,
                delta=portal_tds - documented_tds,
                portal_date=None,
                ledger_canonical_id=None,
                notes="Reconcile per deductor TAN; bank interest TDS may be missing.",
            )
        )

    return ReconciliationReport(
        fy=fy,
        source="26AS",
        matched=matched,
        missing_in_ledger=missing_in_ledger,
        missing_in_portal=missing_in_portal,
        amount_mismatch=amount_mismatch,
        total_portal_amount=portal_tds,
        total_ledger_amount=documented_tds,
        lines=tuple(report_lines),
    )
