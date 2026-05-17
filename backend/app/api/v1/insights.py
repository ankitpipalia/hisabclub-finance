from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.engines.insights.anomaly_detector import find_recent_anomalies
from app.engines.insights.monthly_summary import compute_monthly_summary
from app.engines.insights.reconciliation import build_transfer_reconciliation
from app.engines.insights.recurring_classifier import classify_recurring
from app.engines.insights.recurring_detector import detect_recurring_transactions
from app.engines.insights.tax_compliance import build_tax_compliance_report
from app.engines.insights.trend_analyzer import get_spending_trends
from app.models.insights import MonthlySummary
from app.schemas.insights import (
    AnomalyResponse,
    AnomalyTransaction,
    MonthlySummaryResponse,
    RecomputeResponse,
    ReconciliationResponse,
    RecurringPatternResponse,
    TaxComplianceResponse,
    TrendDataPoint,
    TrendResponse,
)

from sqlalchemy import select

router = APIRouter()


@router.get("/monthly-summary", response_model=MonthlySummaryResponse)
async def get_monthly_summary(
    user: CurrentUser,
    db: DbSession,
    year_month: str | None = Query(
        default=None,
        alias="year_month",
        description="Year-month in YYYY-MM format, e.g. 2026-03. Defaults to current month.",
    ),
    month: str | None = Query(
        default=None,
        description="Year-month in YYYY-MM format, e.g. 2026-03. Defaults to current month.",
        include_in_schema=False,
    ),
):
    """Get or compute monthly summary for a given month."""
    selected_month = year_month or month
    if selected_month is None:
        today = date.today()
        selected_month = f"{today.year:04d}-{today.month:02d}"

    # Check if cached summary exists
    result = await db.execute(
        select(MonthlySummary).where(
            MonthlySummary.user_id == user.id,
            MonthlySummary.year_month == selected_month,
        )
    )
    summary = result.scalar_one_or_none()

    if summary is None:
        summary = await compute_monthly_summary(db, user.id, selected_month)
        await db.commit()

    # Compute vs_last_month (% change in expense)
    vs_last_month = await _compute_vs_last_month(
        db, user.id, selected_month, float(summary.total_expense)
    )

    return MonthlySummaryResponse(
        id=str(summary.id),
        year_month=summary.year_month,
        total_income=float(summary.total_income),
        total_expense=float(summary.total_expense),
        net_flow=float(summary.net_flow),
        category_breakdown=summary.category_breakdown,
        top_merchants=summary.top_merchants,
        transaction_count=summary.transaction_count,
        computed_at=summary.computed_at,
        vs_last_month=vs_last_month,
    )


@router.get("/trends", response_model=TrendResponse)
async def get_trends(
    user: CurrentUser,
    db: DbSession,
    months: int = Query(6, ge=1, le=24, description="Number of months to include"),
):
    """Get spending trends for the last N months."""
    trend_data = await get_spending_trends(db, user.id, months)
    await db.commit()

    return TrendResponse(
        months=months,
        data=[
            TrendDataPoint(
                month=d["month"],
                income=d["income"],
                expense=d["expense"],
                net=d["net"],
                category_breakdown=d["category_breakdown"],
            )
            for d in trend_data
        ],
    )


@router.get("/anomalies", response_model=AnomalyResponse)
async def get_anomalies(
    user: CurrentUser,
    db: DbSession,
    window_days: int = Query(default=30, ge=1, le=180),
    history_days: int = Query(default=90, ge=14, le=720),
    sigma: float = Query(default=2.0, ge=1.0, le=5.0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Detect anomalous spend in the last `window_days`.

    Two detectors run:
      - category_spike: amount > mean + sigma * stddev for that category
      - new_large_merchant: first-ever spend with this merchant_normalized
        above a fixed floor

    No LLM, no background job — runs on-request.
    """
    findings = await find_recent_anomalies(
        db,
        user.id,
        window_days=window_days,
        history_days=history_days,
        sigma=sigma,
        limit=limit,
    )
    items = [AnomalyTransaction(**f.to_dict()) for f in findings]
    return AnomalyResponse(items=items, total=len(items))


@router.get("/recurring", response_model=list[RecurringPatternResponse])
async def get_recurring(user: CurrentUser, db: DbSession):
    """Detect and return recurring transaction patterns."""
    patterns = await detect_recurring_transactions(db, user.id)
    await db.commit()

    results = []
    for p in patterns:
        # Resolve merchant and category names
        merchant_name = None
        if p.merchant:
            merchant_name = p.merchant.display_name
        elif p.description_pattern:
            merchant_name = p.description_pattern

        category_name = None
        if p.category:
            category_name = p.category.name

        results.append(
            RecurringPatternResponse(
                id=str(p.id),
                merchant_name=merchant_name,
                description_pattern=p.description_pattern,
                typical_amount=float(p.typical_amount),
                amount_variance=float(p.amount_variance),
                frequency=p.frequency,
                expected_day=p.expected_day,
                last_seen_date=p.last_seen_date,
                next_expected=p.next_expected,
                is_active=p.is_active,
                category_name=category_name,
                kind=classify_recurring(
                    p.description_pattern or merchant_name or "",
                    category_name,
                ),
            )
        )

    return results


@router.get("/reconciliations", response_model=ReconciliationResponse)
async def get_reconciliations(
    user: CurrentUser,
    db: DbSession,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    max_gap_days: int = Query(5, ge=0, le=15),
    limit: int = Query(300, ge=20, le=3000),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' date must be less than or equal to 'to' date",
        )

    result = await build_transfer_reconciliation(
        db=db,
        user_id=user.id,
        date_from=date_from,
        date_to=date_to,
        max_gap_days=max_gap_days,
        limit=limit,
    )
    return ReconciliationResponse(**result)


@router.get("/tax-compliance", response_model=TaxComplianceResponse)
async def get_tax_compliance(
    user: CurrentUser,
    db: DbSession,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' date must be less than or equal to 'to' date",
        )

    if not date_from or not date_to:
        fy_start, fy_end = _default_financial_year_range(date.today())
        date_from = date_from or fy_start
        date_to = date_to or fy_end

    report = await build_tax_compliance_report(
        db=db,
        user_id=user.id,
        period_start=date_from,
        period_end=date_to,
    )
    return TaxComplianceResponse(**report)


@router.post("/recompute", response_model=RecomputeResponse)
async def recompute_summaries(
    user: CurrentUser,
    db: DbSession,
    months: int = Query(12, ge=1, le=36, description="How many months back to recompute"),
):
    """Force recompute all monthly summaries for the user."""
    today = date.today()
    year = today.year
    month = today.month
    computed = 0

    for _ in range(months):
        year_month = f"{year:04d}-{month:02d}"
        await compute_monthly_summary(db, user.id, year_month)
        computed += 1
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    await db.commit()

    return RecomputeResponse(
        months_computed=computed,
        message=f"Successfully recomputed {computed} monthly summaries.",
    )


async def _compute_vs_last_month(
    db, user_id, current_month: str, current_expense: float
) -> float | None:
    """Compute the % change in total expense vs the previous month."""
    year, month = int(current_month[:4]), int(current_month[5:7])
    month -= 1
    if month == 0:
        month = 12
        year -= 1
    prev_month = f"{year:04d}-{month:02d}"

    result = await db.execute(
        select(MonthlySummary).where(
            MonthlySummary.user_id == user_id,
            MonthlySummary.year_month == prev_month,
        )
    )
    prev_summary = result.scalar_one_or_none()
    if prev_summary is None or float(prev_summary.total_expense) == 0:
        return None

    prev_expense = float(prev_summary.total_expense)
    change_pct = round(((current_expense - prev_expense) / prev_expense) * 100, 2)
    return change_pct


def _default_financial_year_range(today: date) -> tuple[date, date]:
    # India FY runs Apr 1 .. Mar 31.
    if today.month >= 4:
        return date(today.year, 4, 1), date(today.year + 1, 3, 31)
    return date(today.year - 1, 4, 1), date(today.year, 3, 31)
