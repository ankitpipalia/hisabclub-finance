"""Wire-up layer connecting reconciliation engines to user data.

These functions perform DB I/O. They assemble portal totals (from
`tax_portal_data`) and ledger totals (from `canonical_transactions`) and
hand them to the pure-function reconcilers in this package.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.tax.reconcile.ais import reconcile_ais_buckets
from app.engines.tax.reconcile.form16 import reconcile_form16
from app.engines.tax.reconcile.form_26as import (
    reconcile_26as_self_paid_challans,
    reconcile_26as_tds,
)
from app.engines.tax.reconcile.types import ReconciliationReport
from app.models.canonical_transaction import CanonicalTransaction
from app.models.tax_portal_data import TaxPortalData

# Roughly the FY (Apr-Mar). Caller can override.
_TAX_KEYWORDS = ("INCOME TAX", "ITD ", "TIN-PROTEAN", "ADVANCE TAX", "SELF ASSESSMENT")


def _fy_window(financial_year: str) -> tuple[date, date]:
    """Parse FY input to (start, end). Accepts FY24-25, 24-25, 2024-25, etc.

    To stay strict about garbage, the resulting normalized FY must exist in
    the rules registry. The window is Apr 1 of start year → Mar 31 of end.
    """
    from app.engines.tax.rules.registry import _normalize_fy

    normalized = _normalize_fy(financial_year or "")
    inner = normalized[2:]  # strip "FY"
    parts = inner.split("-")
    if len(parts) != 2:
        raise ValueError(f"Unrecognized FY format: {financial_year!r}")
    try:
        start_yr_2digit = int(parts[0])
    except ValueError as exc:
        raise ValueError(f"Unrecognized FY format: {financial_year!r}") from exc
    if not (0 <= start_yr_2digit <= 99):
        raise ValueError(f"Unrecognized FY format: {financial_year!r}")
    start_full = 2000 + start_yr_2digit
    return date(start_full, 4, 1), date(start_full + 1, 3, 31)


async def _ledger_salary_credits(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[tuple[date, Decimal, str]]:
    rows = (
        await db.execute(
            select(CanonicalTransaction).where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.transaction_date >= start,
                CanonicalTransaction.transaction_date <= end,
                CanonicalTransaction.is_excluded == False,  # noqa: E712
            )
        )
    ).scalars().all()
    out: list[tuple[date, Decimal, str]] = []
    for txn in rows:
        nature = (txn.transaction_nature or "").lower()
        merchant = (txn.merchant_raw or "").upper()
        if nature == "income" and ("SALARY" in merchant or "PAYROLL" in merchant):
            out.append(
                (txn.transaction_date, Decimal(str(txn.amount)), str(txn.id))
            )
    return out


async def _ledger_tax_debits(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[tuple[date, Decimal, str]]:
    rows = (
        await db.execute(
            select(CanonicalTransaction).where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.transaction_date >= start,
                CanonicalTransaction.transaction_date <= end,
                CanonicalTransaction.is_excluded == False,  # noqa: E712
                CanonicalTransaction.direction == "debit",
            )
        )
    ).scalars().all()
    out: list[tuple[date, Decimal, str]] = []
    for txn in rows:
        merchant = (txn.merchant_raw or "").upper()
        if any(kw in merchant for kw in _TAX_KEYWORDS):
            out.append(
                (txn.transaction_date, Decimal(str(txn.amount)), str(txn.id))
            )
    return out


async def _ledger_aggregate_by_nature(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> tuple[Decimal, Decimal, Decimal]:
    """Returns (salary, interest, dividend) aggregates from canonical_transactions."""
    rows = (
        await db.execute(
            select(CanonicalTransaction).where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.transaction_date >= start,
                CanonicalTransaction.transaction_date <= end,
                CanonicalTransaction.is_excluded == False,  # noqa: E712
            )
        )
    ).scalars().all()
    salary = Decimal("0")
    interest = Decimal("0")
    dividend = Decimal("0")
    for txn in rows:
        nature = (txn.transaction_nature or "").lower()
        merchant = (txn.merchant_raw or "").upper()
        amt = Decimal(str(txn.amount))
        if nature == "interest_income":
            interest += amt
        elif nature == "dividend_income":
            dividend += amt
        elif nature == "income" and ("SALARY" in merchant or "PAYROLL" in merchant):
            salary += amt
    return salary, interest, dividend


def _read_decimal(
    payload: dict | None, *keys: str, default: Decimal | None = None
) -> Decimal | None:
    """Pull a Decimal from a nested portal payload using the first matching key."""
    if not payload:
        return default
    for key in keys:
        if key in payload:
            value = payload[key]
            if value is None:
                continue
            try:
                return Decimal(str(value))
            except Exception:
                continue
    return default


async def _portal_for(
    db: AsyncSession, user_id: uuid.UUID, financial_year: str, document_type: str
) -> dict | None:
    row = (
        await db.execute(
            select(TaxPortalData).where(
                TaxPortalData.user_id == user_id,
                TaxPortalData.financial_year == financial_year,
                TaxPortalData.document_type == document_type,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.extracted_json or {}


async def _line_items_present(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> dict[str, bool]:
    """Whether any line-item rows exist for the user+FY by source table.

    Used by `run_all_reconciliations` to choose between the line-item
    reconciler (preferred when rows exist) and the aggregate-only fallback.
    """
    from sqlalchemy import select

    from app.models.tax_line_items import (
        AisLineItem,
        Form16Item,
        Form26AsLineItem,
    )

    async def _has(model) -> bool:
        row = (
            await db.execute(
                select(model.id).where(
                    model.user_id == user_id, model.fy == fy
                ).limit(1)
            )
        ).first()
        return row is not None

    return {
        "ais": await _has(AisLineItem),
        "form_26as": await _has(Form26AsLineItem),
        "form_16": await _has(Form16Item),
    }


async def run_all_reconciliations(
    db: AsyncSession, user_id: uuid.UUID, financial_year: str
) -> list[ReconciliationReport]:
    """Assemble inputs + run Form-16, 26AS-TDS, 26AS-self-paid, AIS reconcilers.

    Sprint B.3: when line-item tables are populated for the user+FY, the
    line-item reconcilers run instead of the aggregate-only path. The
    response shape (`ReconciliationReport`) is unchanged so the UI doesn't
    care which path produced the results.

    Reports for sources without any data are still included so the UI can
    render an empty state per source.
    """
    start, end = _fy_window(financial_year)

    f16 = await _portal_for(db, user_id, financial_year, "form_16")
    ais = await _portal_for(db, user_id, financial_year, "ais")
    form_26as = await _portal_for(db, user_id, financial_year, "form_26as")

    # Ledger inputs (only needed for the aggregate path)
    salary_credits = await _ledger_salary_credits(db, user_id, start, end)
    tax_debits = await _ledger_tax_debits(db, user_id, start, end)
    ledger_salary, ledger_interest, ledger_dividend = await _ledger_aggregate_by_nature(
        db, user_id, start, end
    )

    line_items = await _line_items_present(db, user_id, financial_year)
    reports: list[ReconciliationReport] = []

    # ----- Form-16 -----
    if line_items["form_16"]:
        from app.engines.tax.reconcile.line_item import (
            reconcile_form16_line_items,
        )

        reports.append(
            await reconcile_form16_line_items(db, user_id, financial_year)
        )
    else:
        reports.append(
            reconcile_form16(
                fy=financial_year,
                form16_gross_salary=_read_decimal(
                    f16, "gross_salary", "salary", "income_from_salary"
                ),
                ledger_salary_credits=salary_credits,
                employer_name_hint=(f16 or {}).get("employer_name"),
            )
        )

    # ----- 26AS TDS -----
    if line_items["form_26as"]:
        from app.engines.tax.reconcile.line_item import (
            reconcile_form26as_line_items,
        )

        reports.append(
            await reconcile_form26as_line_items(db, user_id, financial_year)
        )
    else:
        reports.append(
            reconcile_26as_tds(
                fy=financial_year,
                portal_tds_total=_read_decimal(form_26as, "tds_total", "tds"),
                form16_tds_total=_read_decimal(f16, "tds_total", "tds"),
                interest_cert_tds_total=None,
            )
        )

    # ----- 26AS self-paid challans (always aggregate; line-item form
    # already merges Part-C rows into the 26AS report above) -----
    reports.append(
        reconcile_26as_self_paid_challans(
            fy=financial_year,
            portal_self_paid_total=_read_decimal(
                form_26as, "self_paid_total", "advance_tax", "self_assessment_tax"
            ),
            ledger_tax_debits=tax_debits,
        )
    )

    # ----- AIS -----
    if line_items["ais"]:
        from app.engines.tax.reconcile.line_item import reconcile_ais_line_items

        reports.append(
            await reconcile_ais_line_items(db, user_id, financial_year)
        )
    else:
        reports.append(
            reconcile_ais_buckets(
                fy=financial_year,
                ais_salary=_read_decimal(ais, "salary", "salary_received"),
                ais_interest=_read_decimal(ais, "interest", "interest_income"),
                ais_dividend=_read_decimal(ais, "dividend", "dividend_income"),
                ais_securities_sold=_read_decimal(
                    ais, "securities_sold", "sale_of_securities"
                ),
                ledger_salary=ledger_salary,
                ledger_interest=ledger_interest,
                ledger_dividend=ledger_dividend,
            )
        )

    return reports
