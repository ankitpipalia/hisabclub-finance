from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.engines.insights import subscriptions as subscriptions_engine


@pytest.mark.asyncio
async def test_build_subscription_overview_computes_summary(monkeypatch):
    today = date.today()

    async def _fake_detect(_db, _user_id):
        return [
            SimpleNamespace(
                id=uuid.uuid4(),
                merchant=None,
                category=SimpleNamespace(name="Streaming"),
                description_pattern="Netflix",
                typical_amount=499.0,
                amount_variance=0.02,
                frequency="monthly",
                expected_day=7,
                last_seen_date=today - timedelta(days=27),
                next_expected=today + timedelta(days=2),
                is_active=True,
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                merchant=SimpleNamespace(display_name="Adobe"),
                category=SimpleNamespace(name="Software"),
                description_pattern="ADOBE",
                typical_amount=2399.0,
                amount_variance=0.0,
                frequency="yearly",
                expected_day=12,
                last_seen_date=today - timedelta(days=360),
                next_expected=today - timedelta(days=3),
                is_active=True,
            ),
        ]

    monkeypatch.setattr(subscriptions_engine, "detect_recurring_transactions", _fake_detect)

    payload = await subscriptions_engine.build_subscription_overview(
        db=object(),
        user_id=uuid.uuid4(),
    )

    assert payload["summary"]["active_count"] == 2
    assert payload["summary"]["overdue_count"] == 1
    assert payload["summary"]["total_annual_estimate"] == 8387.0
    assert payload["items"][0]["status"] == "overdue"
