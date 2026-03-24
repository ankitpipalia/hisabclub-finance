"""Auto-create Bill records from parsed statements."""

from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill
from app.models.statement import Statement


async def create_bill_from_statement(
    db: AsyncSession,
    user_id: uuid.UUID,
    statement: Statement,
) -> Bill | None:
    """Create a Bill record from a parsed statement if it has billing info.

    Returns the created Bill, or None if the statement lacks due_date/total_amount_due
    or a duplicate bill already exists.
    """
    if not statement.due_date or not statement.total_amount_due:
        return None

    # Check for existing bill with same bank + billing period to avoid duplicates
    existing_query = select(Bill).where(
        and_(
            Bill.user_id == user_id,
            Bill.bank_name == statement.bank_name,
            Bill.due_date == statement.due_date,
        )
    )
    if statement.account_number_masked:
        existing_query = existing_query.where(
            Bill.account_masked == statement.account_number_masked
        )

    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        return None

    bill = Bill(
        user_id=user_id,
        bank_name=statement.bank_name,
        account_masked=statement.account_number_masked,
        statement_id=statement.id,
        billing_period_start=statement.statement_period_start,
        billing_period_end=statement.statement_period_end,
        due_date=statement.due_date,
        total_due=statement.total_amount_due,
        min_due=statement.min_amount_due,
    )
    db.add(bill)
    await db.flush()

    return bill
