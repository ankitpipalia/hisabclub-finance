from datetime import datetime

from pydantic import BaseModel, Field


class BudgetCreateRequest(BaseModel):
    category_id: str | None = None  # NULL = overall budget
    amount_limit: float = Field(..., gt=0)
    period: str = Field(..., pattern="^(monthly|yearly)$")


class BudgetUpdateRequest(BaseModel):
    amount_limit: float | None = Field(None, gt=0)
    is_active: bool | None = None


class BudgetResponse(BaseModel):
    id: str
    category_id: str | None
    category_name: str | None = None
    amount_limit: float
    period: str
    is_active: bool
    spent_amount: float = 0.0
    remaining: float = 0.0
    percentage_used: float = 0.0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]
    total: int
