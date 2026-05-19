"""Missing-document checklist (Sprint B.4).

Walks the user's FY data and emits a typed list of "what's blocking ITR
preparation". Each item carries a severity, a CTA link, and an evidence
count so the dashboard can prioritise.

Severity ordering:
  - "block_filing" — without this you cannot file accurately.
  - "warning"      — affects reconciliation match rate but ITR still possible.
  - "info"         — nice-to-have for completeness.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.statement_period_coverage import StatementPeriodCoverage
from app.models.tax_line_items import (
    AisLineItem,
    Form16Item,
    Form26AsLineItem,
)
from app.models.tax_portal_data import TaxPortalData


@dataclass(frozen=True)
class ChecklistItem:
    kind: str  # e.g. "MISSING_AIS"
    severity: str  # "block_filing" | "warning" | "info"
    title: str
    detail: str
    cta_link: str | None = None
    evidence_count: int = 0


@dataclass(frozen=True)
class ChecklistResponse:
    fy: str
    items: tuple[ChecklistItem, ...] = field(default_factory=tuple)


async def _count(db: AsyncSession, stmt) -> int:
    row = (await db.execute(select(func.count()).select_from(stmt.subquery()))).first()
    return int(row[0]) if row else 0


async def build_checklist(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> ChecklistResponse:
    items: list[ChecklistItem] = []

    # 1. AIS
    ais_count = await _count(
        db,
        select(AisLineItem.id).where(
            AisLineItem.user_id == user_id, AisLineItem.fy == fy
        ),
    )
    has_ais_aggregate = (
        await db.execute(
            select(TaxPortalData.id).where(
                TaxPortalData.user_id == user_id,
                TaxPortalData.financial_year == fy,
                TaxPortalData.document_type == "ais",
            ).limit(1)
        )
    ).first() is not None
    if ais_count == 0 and not has_ais_aggregate:
        items.append(
            ChecklistItem(
                kind="MISSING_AIS",
                severity="block_filing",
                title="Upload AIS",
                detail=(
                    "AIS is the IT department's record of every financial "
                    "transaction reported under your PAN. Without it, "
                    "HisabClub can't verify your income / interest / "
                    "dividend lines."
                ),
                cta_link="/tax?upload=ais",
            )
        )

    # 2. 26AS
    f26_count = await _count(
        db,
        select(Form26AsLineItem.id).where(
            Form26AsLineItem.user_id == user_id, Form26AsLineItem.fy == fy
        ),
    )
    has_26as_aggregate = (
        await db.execute(
            select(TaxPortalData.id).where(
                TaxPortalData.user_id == user_id,
                TaxPortalData.financial_year == fy,
                TaxPortalData.document_type == "form_26as",
            ).limit(1)
        )
    ).first() is not None
    if f26_count == 0 and not has_26as_aggregate:
        items.append(
            ChecklistItem(
                kind="MISSING_26AS",
                severity="block_filing",
                title="Upload Form 26AS",
                detail=(
                    "Form 26AS lists every TDS deduction made against your "
                    "PAN. Required to verify TDS credits during ITR filing."
                ),
                cta_link="/tax?upload=form_26as",
            )
        )

    # 3. Form-16
    f16_count = await _count(
        db,
        select(Form16Item.id).where(
            Form16Item.user_id == user_id, Form16Item.fy == fy
        ),
    )
    has_f16_aggregate = (
        await db.execute(
            select(TaxPortalData.id).where(
                TaxPortalData.user_id == user_id,
                TaxPortalData.financial_year == fy,
                TaxPortalData.document_type == "form_16",
            ).limit(1)
        )
    ).first() is not None
    # If AIS says salary exists but no Form-16 → block
    ais_salary_exists = (
        await db.execute(
            select(AisLineItem.id).where(
                AisLineItem.user_id == user_id,
                AisLineItem.fy == fy,
                AisLineItem.category == "salary",
            ).limit(1)
        )
    ).first() is not None
    if not has_f16_aggregate and f16_count == 0:
        items.append(
            ChecklistItem(
                kind="MISSING_FORM_16",
                severity="block_filing" if ais_salary_exists else "warning",
                title="Upload Form-16 (Part A + B)",
                detail=(
                    "Form-16 documents your salary income + TDS + Sec 80x "
                    "deductions claimed via payroll. "
                    + (
                        "Your AIS reports salary income — Form-16 is required."
                        if ais_salary_exists
                        else "Required if you have salary income."
                    )
                ),
                cta_link="/tax?upload=form_16",
            )
        )

    # 4. Form-16A — flagged if 26AS has TDS rows under section 194/194A/194K
    # but no Form-16A has been uploaded.
    f16a_required_sections = (
        (
            await db.execute(
                select(Form26AsLineItem.section).where(
                    Form26AsLineItem.user_id == user_id,
                    Form26AsLineItem.fy == fy,
                    Form26AsLineItem.section.in_(["194", "194A", "194K"]),
                )
            )
        )
        .scalars()
        .all()
    )
    if f16a_required_sections:
        items.append(
            ChecklistItem(
                kind="MISSING_FORM_16A",
                severity="warning",
                title="Upload Form-16A",
                detail=(
                    f"Your 26AS shows TDS under sections "
                    f"{sorted(set(f16a_required_sections))} — Form-16A from "
                    "each deductor is required to reconcile interest / "
                    "dividend TDS amounts."
                ),
                cta_link="/tax?upload=form_16a",
                evidence_count=len(set(f16a_required_sections)),
            )
        )

    # 5. Capital-gains evidence
    cg_lines = (
        await db.execute(
            select(AisLineItem.id).where(
                AisLineItem.user_id == user_id,
                AisLineItem.fy == fy,
                AisLineItem.category == "securities_sold",
            ).limit(1)
        )
    ).first()
    if cg_lines is not None:
        items.append(
            ChecklistItem(
                kind="MISSING_CG_DOC",
                severity="warning",
                title="Upload broker / MF P&L statement",
                detail=(
                    "AIS reports securities sold — HisabClub needs your "
                    "broker P&L or MF CAS to compute STCG / LTCG with the "
                    "right per-FY rates."
                ),
                cta_link="/imports?type=demat",
            )
        )

    # 6. Interest certificate
    interest_lines = (
        await db.execute(
            select(AisLineItem).where(
                AisLineItem.user_id == user_id,
                AisLineItem.fy == fy,
                AisLineItem.category == "interest",
            )
        )
    ).scalars().all()
    if interest_lines:
        # Heuristic: if no bank-statement coverage exists and no interest
        # certificate has been uploaded as a tax document, flag it.
        items.append(
            ChecklistItem(
                kind="MISSING_INTEREST_CERT",
                severity="info",
                title="Upload bank interest certificate",
                detail=(
                    "AIS reports interest income — uploading the bank's "
                    "interest certificate makes the 80TTA/80TTB section limits "
                    "easier to apply."
                ),
                cta_link="/imports?type=interest_certificate",
                evidence_count=len(interest_lines),
            )
        )

    # 7. Statement coverage
    coverage_rows = (
        await db.execute(
            select(StatementPeriodCoverage).where(
                StatementPeriodCoverage.user_id == user_id,
            )
        )
    ).scalars().all()
    if not coverage_rows:
        items.append(
            ChecklistItem(
                kind="MISSING_BANK_STATEMENTS",
                severity="warning",
                title="Upload bank statements for the FY",
                detail=(
                    "No statement coverage records yet — upload bank "
                    "statements so HisabClub can reconcile income, interest, "
                    "and tax debits against AIS / 26AS."
                ),
                cta_link="/upload",
            )
        )
    else:
        # Naive check: do we have any canonical txn in the FY-window?
        from app.engines.tax.reconcile.wire import _fy_window

        try:
            start, end = _fy_window(fy)
        except ValueError:
            start = end = None
        if start and end:
            txn_count = await _count(
                db,
                select(CanonicalTransaction.id).where(
                    CanonicalTransaction.user_id == user_id,
                    CanonicalTransaction.transaction_date >= start,
                    CanonicalTransaction.transaction_date <= end,
                    CanonicalTransaction.is_excluded == False,  # noqa: E712
                ),
            )
            if txn_count < 10:
                items.append(
                    ChecklistItem(
                        kind="LOW_LEDGER_COVERAGE",
                        severity="warning",
                        title="Very few transactions in ledger",
                        detail=(
                            f"Only {txn_count} canonical transactions in FY "
                            f"{fy}. Upload more bank/CC statements to improve "
                            "reconciliation."
                        ),
                        cta_link="/upload",
                        evidence_count=txn_count,
                    )
                )

    return ChecklistResponse(fy=fy, items=tuple(items))
