import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import insights as insights_api


class _DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DummyDb:
    def __init__(self, existing_summary=None):
        self._existing_summary = existing_summary
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return _DummyResult(self._existing_summary)

    async def commit(self):
        self.commits += 1


def _summary_for(month: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        year_month=month,
        total_income=0,
        total_expense=100,
        net_flow=-100,
        category_breakdown={},
        top_merchants=[],
        transaction_count=1,
        computed_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_monthly_summary_prefers_year_month(monkeypatch):
    captured = {}

    async def _fake_compute(_db, _user_id, ym):
        captured["ym"] = ym
        return _summary_for(ym)

    async def _fake_vs(*_args, **_kwargs):
        return None

    monkeypatch.setattr(insights_api, "compute_monthly_summary", _fake_compute)
    monkeypatch.setattr(insights_api, "_compute_vs_last_month", _fake_vs)

    db = _DummyDb(existing_summary=None)
    user = SimpleNamespace(id=uuid.uuid4())
    response = await insights_api.get_monthly_summary(
        user=user,
        db=db,
        year_month="2025-03",
        month="2025-02",
    )

    assert captured["ym"] == "2025-03"
    assert response.year_month == "2025-03"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_monthly_summary_accepts_legacy_month_param(monkeypatch):
    captured = {}

    async def _fake_compute(_db, _user_id, ym):
        captured["ym"] = ym
        return _summary_for(ym)

    async def _fake_vs(*_args, **_kwargs):
        return None

    monkeypatch.setattr(insights_api, "compute_monthly_summary", _fake_compute)
    monkeypatch.setattr(insights_api, "_compute_vs_last_month", _fake_vs)

    db = _DummyDb(existing_summary=None)
    user = SimpleNamespace(id=uuid.uuid4())
    response = await insights_api.get_monthly_summary(
        user=user,
        db=db,
        year_month=None,
        month="2025-02",
    )

    assert captured["ym"] == "2025-02"
    assert response.year_month == "2025-02"
    assert db.commits == 1
