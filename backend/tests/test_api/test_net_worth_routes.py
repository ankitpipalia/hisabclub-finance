from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.api.v1 import net_worth as net_worth_api


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.added = []
        self.flush_count = 0
        self.deleted = []

    async def execute(self, *_args, **_kwargs):
        return self.responses.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_create_manual_snapshot_generates_position_key():
    user = SimpleNamespace(id=uuid.uuid4())
    db = _FakeDb()

    response = await net_worth_api.create_manual_snapshot(
        net_worth_api.ManualBalanceSnapshotCreateRequest(
            label="Emergency Fund",
            entry_kind="asset",
            asset_type="cash",
            balance=250000,
            as_of_date=date(2026, 4, 6),
        ),
        user=user,
        db=db,
    )

    assert response.position_key == "asset-cash-emergency-fund"
    assert db.flush_count == 1
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_get_net_worth_overview_serializes_totals(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    snapshot = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=None,
        statement_id=None,
        position_key="asset-cash-emergency-fund",
        label="Emergency Fund",
        source_kind="manual",
        entry_kind="asset",
        asset_type="cash",
        institution_name=None,
        account_masked=None,
        currency="INR",
        balance=125000.0,
        as_of_date=date(2026, 4, 6),
        is_active=True,
        metadata_json=None,
        created_at=date(2026, 4, 6),
    )
    db = _FakeDb([_ScalarsResult([snapshot])])

    async def _fake_sync(*_args, **_kwargs):
        return 1

    monkeypatch.setattr(net_worth_api, "sync_statement_balance_snapshots", _fake_sync)

    response = await net_worth_api.get_net_worth_overview(user=user, db=db, months=12)

    assert response.totals.assets == 125000.0
    assert response.totals.net_worth == 125000.0
    assert len(response.positions) == 1


@pytest.mark.asyncio
async def test_delete_manual_snapshot_404_when_missing():
    user = SimpleNamespace(id=uuid.uuid4())
    db = _FakeDb([_ScalarOneOrNoneResult(None)])

    with pytest.raises(net_worth_api.HTTPException) as exc:
        await net_worth_api.delete_manual_snapshot(str(uuid.uuid4()), user=user, db=db)

    assert exc.value.status_code == 404
