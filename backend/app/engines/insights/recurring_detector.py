import uuid
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, stdev

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.insights import RecurringPattern


async def detect_recurring_transactions(
    db: AsyncSession, user_id: uuid.UUID
) -> list[RecurringPattern]:
    """
    Detect recurring transactions for a user by grouping by merchant
    and analyzing amount similarity and date regularity.
    """
    # Fetch all non-excluded transactions ordered by date
    result = await db.execute(
        select(CanonicalTransaction)
        .where(
            CanonicalTransaction.user_id == user_id,
            CanonicalTransaction.is_excluded == False,  # noqa: E712
            CanonicalTransaction.transaction_nature == "expense",
        )
        .order_by(CanonicalTransaction.transaction_date.asc())
    )
    transactions = result.scalars().all()

    # Group by merchant (normalized name or raw)
    merchant_groups: dict[str, list[CanonicalTransaction]] = defaultdict(list)
    for t in transactions:
        key = t.merchant_normalized or t.merchant_raw
        merchant_groups[key].append(t)

    # Clear existing recurring patterns for this user
    await db.execute(
        delete(RecurringPattern).where(RecurringPattern.user_id == user_id)
    )

    patterns: list[RecurringPattern] = []

    for merchant_name, txns in merchant_groups.items():
        if len(txns) < 2:
            continue

        # Check amount similarity: within 20% variance of mean
        amounts = [float(t.amount) for t in txns]
        avg_amount = mean(amounts)
        if avg_amount == 0:
            continue

        max_deviation = max(abs(a - avg_amount) for a in amounts)
        variance_ratio = max_deviation / avg_amount

        if variance_ratio > 0.20:
            continue

        # Check date regularity: compute gaps between consecutive transactions
        dates = sorted([t.transaction_date for t in txns])
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

        if not gaps:
            continue

        avg_gap = mean(gaps)

        # Determine frequency based on average gap
        frequency = _classify_frequency(avg_gap)
        if frequency is None:
            continue

        # Compute amount variance as coefficient of variation
        if len(amounts) >= 2:
            amount_var = stdev(amounts) / avg_amount if avg_amount > 0 else 0
        else:
            amount_var = 0

        # Typical day of month
        days_of_month = [d.day for d in dates]
        expected_day = round(mean(days_of_month))

        last_seen = dates[-1]
        next_expected = _compute_next_expected(last_seen, frequency, expected_day)

        # Get category and merchant_id from most recent transaction
        most_recent = txns[-1]

        pattern = RecurringPattern(
            user_id=user_id,
            merchant_id=most_recent.merchant_id,
            description_pattern=merchant_name,
            typical_amount=round(avg_amount, 2),
            amount_variance=round(amount_var, 4),
            frequency=frequency,
            expected_day=expected_day,
            last_seen_date=last_seen,
            next_expected=next_expected,
            is_active=True,
            category_id=most_recent.category_id,
        )
        db.add(pattern)
        patterns.append(pattern)

    await db.flush()
    return patterns


def _classify_frequency(avg_gap: float) -> str | None:
    """Classify the frequency based on average gap in days."""
    if 25 <= avg_gap <= 35:
        return "monthly"
    elif 80 <= avg_gap <= 100:
        return "quarterly"
    elif 340 <= avg_gap <= 390:
        return "yearly"
    return None


def _compute_next_expected(last_seen: date, frequency: str, expected_day: int) -> date:
    """Compute the next expected date based on frequency."""
    if frequency == "monthly":
        month = last_seen.month + 1
        year = last_seen.year
        if month > 12:
            month = 1
            year += 1
    elif frequency == "quarterly":
        month = last_seen.month + 3
        year = last_seen.year
        while month > 12:
            month -= 12
            year += 1
    elif frequency == "yearly":
        month = last_seen.month
        year = last_seen.year + 1
    else:
        month = last_seen.month + 1
        year = last_seen.year
        if month > 12:
            month = 1
            year += 1

    # Clamp day to valid range for the target month
    import calendar

    max_day = calendar.monthrange(year, month)[1]
    day = min(expected_day, max_day)

    return date(year, month, day)
