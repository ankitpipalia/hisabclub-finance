import uuid
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.insights import MonthlySummary


async def compute_monthly_summary(
    db: AsyncSession, user_id: uuid.UUID, year_month: str
) -> MonthlySummary:
    """
    Compute monthly summary for a given user and year-month (e.g. '2026-03').
    Upserts into the monthly_summaries table.
    """
    # Parse year_month into date range
    year, month = int(year_month[:4]), int(year_month[5:7])
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # Fetch all non-excluded transactions for the user in this month
    txn_query = select(CanonicalTransaction).where(
        CanonicalTransaction.user_id == user_id,
        CanonicalTransaction.is_excluded == False,  # noqa: E712
        CanonicalTransaction.transaction_date >= month_start,
        CanonicalTransaction.transaction_date < month_end,
    )
    result = await db.execute(txn_query)
    transactions = result.scalars().all()

    # Compute totals from semantic nature rather than raw debit/credit.
    # This excludes internal transfers (e.g., credit-card bill settlements).
    total_income = sum(float(t.amount) for t in transactions if t.transaction_nature == "income")
    total_expense = sum(float(t.amount) for t in transactions if t.transaction_nature == "expense")
    net_flow = total_income - total_expense
    transaction_count = len(transactions)

    # Category breakdown (debits only)
    category_ids = {
        t.category_id for t in transactions if t.transaction_nature == "expense" and t.category_id
    }
    category_names: dict[uuid.UUID, str] = {}
    if category_ids:
        cat_result = await db.execute(
            select(Category.id, Category.name).where(Category.id.in_(category_ids))
        )
        category_names = {row[0]: row[1] for row in cat_result.all()}

    category_breakdown: dict[str, float] = {}
    for t in transactions:
        if t.transaction_nature == "expense":
            cat_name = category_names.get(t.category_id, "Uncategorized")
            category_breakdown[cat_name] = category_breakdown.get(cat_name, 0) + float(t.amount)

    # Round category breakdown values
    category_breakdown = {k: round(v, 2) for k, v in category_breakdown.items()}

    # Top merchants by amount (debits only)
    merchant_data: dict[str, dict] = {}
    for t in transactions:
        if t.transaction_nature == "expense":
            name = t.merchant_normalized or t.merchant_raw
            if name not in merchant_data:
                merchant_data[name] = {"name": name, "amount": 0.0, "count": 0}
            merchant_data[name]["amount"] += float(t.amount)
            merchant_data[name]["count"] += 1

    # Sort by amount descending, take top 10
    top_merchants = sorted(merchant_data.values(), key=lambda m: m["amount"], reverse=True)[:10]
    for m in top_merchants:
        m["amount"] = round(m["amount"], 2)

    # Upsert into monthly_summaries
    stmt = pg_insert(MonthlySummary).values(
        id=uuid.uuid4(),
        user_id=user_id,
        year_month=year_month,
        total_income=round(total_income, 2),
        total_expense=round(total_expense, 2),
        net_flow=round(net_flow, 2),
        category_breakdown=category_breakdown,
        top_merchants=top_merchants,
        transaction_count=transaction_count,
        computed_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_monthly_summary_user_month",
        set_={
            "total_income": stmt.excluded.total_income,
            "total_expense": stmt.excluded.total_expense,
            "net_flow": stmt.excluded.net_flow,
            "category_breakdown": stmt.excluded.category_breakdown,
            "top_merchants": stmt.excluded.top_merchants,
            "transaction_count": stmt.excluded.transaction_count,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    await db.execute(stmt)
    await db.flush()

    # Fetch the upserted row
    result = await db.execute(
        select(MonthlySummary).where(
            MonthlySummary.user_id == user_id,
            MonthlySummary.year_month == year_month,
        )
    )
    return result.scalar_one()
