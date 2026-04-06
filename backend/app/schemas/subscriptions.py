from datetime import date

from pydantic import BaseModel, Field


class SubscriptionItemResponse(BaseModel):
    id: str
    merchant_name: str
    description_pattern: str
    category_name: str | None = None
    typical_amount: float
    amount_variance: float
    frequency: str
    expected_day: int
    last_seen_date: date
    next_expected: date
    is_active: bool
    annual_cost_estimate: float
    monthly_cost_equivalent: float
    status: str
    days_until_due: int


class SubscriptionSummaryResponse(BaseModel):
    active_count: int
    total_monthly_estimate: float
    total_annual_estimate: float
    overdue_count: int


class SubscriptionOverviewResponse(BaseModel):
    summary: SubscriptionSummaryResponse
    items: list[SubscriptionItemResponse] = Field(default_factory=list)
