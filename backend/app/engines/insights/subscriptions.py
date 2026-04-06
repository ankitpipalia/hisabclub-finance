from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.insights.recurring_detector import detect_recurring_transactions


def _annual_multiplier(frequency: str) -> int:
    normalized = (frequency or "").strip().lower()
    if normalized == "monthly":
        return 12
    if normalized == "quarterly":
        return 4
    if normalized == "yearly":
        return 1
    return 12


def _subscription_status(next_expected: date, is_active: bool) -> str:
    if not is_active:
        return "inactive"
    today = date.today()
    if next_expected < today:
        return "overdue"
    if (next_expected - today).days <= 7:
        return "upcoming"
    return "scheduled"


async def build_subscription_overview(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> dict[str, object]:
    patterns = await detect_recurring_transactions(db, user_id)

    items: list[dict[str, object]] = []
    total_monthly = 0.0
    total_annual = 0.0

    for pattern in patterns:
        merchant_name = (
            pattern.merchant.display_name
            if getattr(pattern, "merchant", None) is not None
            else pattern.description_pattern
        )
        category_name = (
            pattern.category.name if getattr(pattern, "category", None) is not None else None
        )
        annual_cost = round(float(pattern.typical_amount) * _annual_multiplier(pattern.frequency), 2)
        monthly_equivalent = round(annual_cost / 12, 2)
        total_monthly += monthly_equivalent
        total_annual += annual_cost
        items.append(
            {
                "id": str(pattern.id),
                "merchant_name": merchant_name,
                "description_pattern": pattern.description_pattern,
                "category_name": category_name,
                "typical_amount": round(float(pattern.typical_amount), 2),
                "amount_variance": round(float(pattern.amount_variance), 4),
                "frequency": pattern.frequency,
                "expected_day": pattern.expected_day,
                "last_seen_date": pattern.last_seen_date,
                "next_expected": pattern.next_expected,
                "is_active": bool(pattern.is_active),
                "annual_cost_estimate": annual_cost,
                "monthly_cost_equivalent": monthly_equivalent,
                "status": _subscription_status(pattern.next_expected, bool(pattern.is_active)),
                "days_until_due": (pattern.next_expected - date.today()).days,
            }
        )

    items.sort(key=lambda item: (item["status"] != "overdue", item["days_until_due"], item["merchant_name"]))
    return {
        "summary": {
            "active_count": sum(1 for item in items if item["is_active"]),
            "total_monthly_estimate": round(total_monthly, 2),
            "total_annual_estimate": round(total_annual, 2),
            "overdue_count": sum(1 for item in items if item["status"] == "overdue"),
        },
        "items": items,
    }
