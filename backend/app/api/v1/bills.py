from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.sql import func

from app.dependencies import CurrentUser, DbSession
from app.models.bill import Bill
from app.schemas.bill import (
    BillCreateRequest,
    BillListResponse,
    BillResponse,
    BillUpdateRequest,
)

router = APIRouter()


def _bill_to_response(bill: Bill) -> BillResponse:
    today = date.today()
    days_until_due = (bill.due_date - today).days if not bill.is_paid else None

    return BillResponse(
        id=str(bill.id),
        bank_name=bill.bank_name,
        account_masked=bill.account_masked,
        billing_period_start=bill.billing_period_start,
        billing_period_end=bill.billing_period_end,
        due_date=bill.due_date,
        total_due=float(bill.total_due),
        min_due=float(bill.min_due) if bill.min_due is not None else None,
        is_paid=bill.is_paid,
        paid_amount=float(bill.paid_amount) if bill.paid_amount is not None else None,
        paid_date=bill.paid_date,
        days_until_due=days_until_due,
        created_at=bill.created_at,
    )


@router.get("", response_model=BillListResponse)
async def list_bills(
    user: CurrentUser,
    db: DbSession,
    bill_status: str = Query("all", alias="status", pattern="^(unpaid|paid|upcoming|all)$"),
):
    query = select(Bill).where(Bill.user_id == user.id)

    if bill_status in ("unpaid", "upcoming"):
        query = query.where(Bill.is_paid == False)  # noqa: E712
    elif bill_status == "paid":
        query = query.where(Bill.is_paid == True)  # noqa: E712

    query = query.order_by(Bill.due_date.asc())

    result = await db.execute(query)
    bills = result.scalars().all()

    return BillListResponse(
        items=[_bill_to_response(b) for b in bills],
        total=len(bills),
    )


@router.post("", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create_bill(
    request: BillCreateRequest, user: CurrentUser, db: DbSession
):
    bill = Bill(
        user_id=user.id,
        bank_name=request.bank_name,
        account_masked=request.account_masked,
        billing_period_start=request.billing_period_start,
        billing_period_end=request.billing_period_end,
        due_date=request.due_date,
        total_due=request.total_due,
        min_due=request.min_due,
    )
    db.add(bill)
    await db.flush()

    return _bill_to_response(bill)


@router.patch("/{bill_id}", response_model=BillResponse)
async def update_bill(
    bill_id: str,
    request: BillUpdateRequest,
    user: CurrentUser,
    db: DbSession,
):
    result = await db.execute(
        select(Bill).where(Bill.id == bill_id, Bill.user_id == user.id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(bill, field, value)

    await db.flush()
    return _bill_to_response(bill)
