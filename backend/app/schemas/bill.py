from datetime import date, datetime

from pydantic import BaseModel, Field


class BillCreateRequest(BaseModel):
    bank_name: str
    account_masked: str | None = None
    billing_period_start: date | None = None
    billing_period_end: date | None = None
    due_date: date
    total_due: float = Field(..., gt=0)
    min_due: float | None = None


class BillUpdateRequest(BaseModel):
    is_paid: bool | None = None
    paid_amount: float | None = None
    paid_date: date | None = None


class BillResponse(BaseModel):
    id: str
    bank_name: str
    account_masked: str | None
    billing_period_start: date | None
    billing_period_end: date | None
    due_date: date
    total_due: float
    min_due: float | None
    is_paid: bool
    paid_amount: float | None
    paid_date: date | None
    days_until_due: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class BillListResponse(BaseModel):
    items: list[BillResponse]
    total: int
