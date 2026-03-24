import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.insights.monthly_summary import compute_monthly_summary
from app.models.insights import MonthlySummary


async def get_spending_trends(
    db: AsyncSession, user_id: uuid.UUID, months: int = 6
) -> list[dict]:
    """
    Get monthly spending trends for the last N months.
    If summaries don't exist, compute them on the fly.
    """
    today = date.today()
    year_months = _get_last_n_months(today, months)

    # Check which summaries already exist
    result = await db.execute(
        select(MonthlySummary).where(
            MonthlySummary.user_id == user_id,
            MonthlySummary.year_month.in_(year_months),
        )
    )
    existing = {s.year_month: s for s in result.scalars().all()}

    # Compute missing summaries
    for ym in year_months:
        if ym not in existing:
            summary = await compute_monthly_summary(db, user_id, ym)
            existing[ym] = summary

    # Build trend data in chronological order
    trend_data = []
    for ym in year_months:
        s = existing[ym]
        trend_data.append(
            {
                "month": s.year_month,
                "income": float(s.total_income),
                "expense": float(s.total_expense),
                "net": float(s.net_flow),
                "category_breakdown": s.category_breakdown,
            }
        )

    return trend_data


def _get_last_n_months(today: date, n: int) -> list[str]:
    """Return a list of year-month strings for the last N months, including the current month."""
    result = []
    year = today.year
    month = today.month
    for _ in range(n):
        result.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    result.reverse()
    return result
