from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.insights.tax_compliance import build_tax_compliance_report
from app.models.tax_portal_data import TaxPortalData


def _fy_bounds(financial_year: str) -> tuple[date, date]:
    value = (financial_year or "").strip()
    if not value:
        raise ValueError("financial_year is required")
    if "-" not in value:
        raise ValueError("financial_year must look like 2025-26")
    start_token, end_token = value.split("-", 1)
    start_year = int(start_token)
    end_suffix = int(end_token)
    end_year = 2000 + end_suffix if end_suffix < 100 else end_suffix
    return date(start_year, 4, 1), date(end_year, 3, 31)


async def cross_verify_tax(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    financial_year: str,
) -> dict:
    period_start, period_end = _fy_bounds(financial_year)
    tax_report = await build_tax_compliance_report(
        db=db,
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
    )
    portal_rows = (
        await db.execute(
            select(TaxPortalData).where(
                TaxPortalData.user_id == user_id,
                TaxPortalData.financial_year == financial_year,
            )
        )
    ).scalars().all()

    portal_totals = {
        "salary_income": 0.0,
        "interest_income": 0.0,
        "dividend_income": 0.0,
        "tds_total": 0.0,
        "tax_paid_total": 0.0,
    }
    for row in portal_rows:
        payload = row.extracted_json or {}
        portal_totals["salary_income"] += float(payload.get("salary_income") or payload.get("gross_salary") or 0.0)
        portal_totals["interest_income"] += float(payload.get("interest_income") or payload.get("interest_amount") or 0.0)
        portal_totals["dividend_income"] += float(payload.get("dividend_income") or 0.0)
        portal_totals["tds_total"] += float(payload.get("tds_total") or payload.get("tds_amount") or 0.0)
        portal_totals["tax_paid_total"] += float(payload.get("tax_paid_total") or payload.get("tax_paid_amount") or 0.0)

    totals = tax_report["totals"]
    checks = [
        _build_check("total_income", float(totals["total_income"]), portal_totals["salary_income"] + portal_totals["interest_income"] + portal_totals["dividend_income"], 1000.0, "Compares ledger income with uploaded portal income documents."),
        _build_check("salary_income", float(totals["salary_income"]), portal_totals["salary_income"], 500.0, "Compares salary-like ledger credits with Form 16 / AIS salary totals."),
        _build_check("interest_income", float(totals["interest_income"]), portal_totals["interest_income"], 100.0, "Compares bank interest in ledger with AIS / interest certificates."),
        _build_check("tds_deducted", float(totals["documented_interest_tds"]), portal_totals["tds_total"], 100.0, "Compares documented TDS in app with Form 26AS / Form 16 totals."),
        _build_check("advance_tax_paid", float(totals["tax_payments"]), portal_totals["tax_paid_total"], 0.0, "Compares tax payments in ledger with challan / 26AS data."),
    ]
    discrepancies = [check for check in checks if check["status"] != "match"]
    return {
        "financial_year": financial_year,
        "tax_report": tax_report,
        "portal_data": portal_rows,
        "checks": checks,
        "discrepancies": discrepancies,
    }


def _build_check(check: str, app_amount: float, portal_amount: float, tolerance: float, detail: str) -> dict:
    gap = round(app_amount - portal_amount, 2)
    status = "match" if abs(gap) <= tolerance else "mismatch"
    if app_amount == 0 and portal_amount == 0:
        status = "unverified"
    return {
        "check": check,
        "status": status,
        "app_amount": round(app_amount, 2),
        "portal_amount": round(portal_amount, 2),
        "gap": gap,
        "detail": detail,
    }
