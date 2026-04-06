from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.engines.insights.net_worth import (
    build_net_worth_history,
    build_statement_snapshot_seed,
    summarize_latest_positions,
)


def _statement(**overrides):
    now = datetime(2026, 4, 6, tzinfo=timezone.utc)
    payload = {
        "id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "bank_name": "ICICI",
        "account_type": "savings",
        "account_number_masked": "XX9719",
        "closing_balance": 186543.22,
        "total_amount_due": None,
        "currency": "INR",
        "statement_period_start": date(2026, 3, 1),
        "statement_period_end": date(2026, 3, 31),
        "parsed_at": now,
        "created_at": now,
        "parse_status": "parsed",
        "is_active": True,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _snapshot(position_key: str, as_of_date: date, balance: float, entry_kind: str = "asset", **extra):
    now = datetime(2026, 4, 6, tzinfo=timezone.utc)
    payload = {
        "id": uuid.uuid4(),
        "position_key": position_key,
        "as_of_date": as_of_date,
        "created_at": now,
        "balance": balance,
        "entry_kind": entry_kind,
        "label": position_key,
        "source_kind": "statement",
    }
    payload.update(extra)
    return SimpleNamespace(**payload)


def test_build_statement_snapshot_seed_for_savings_uses_closing_balance():
    seed = build_statement_snapshot_seed(_statement())

    assert seed is not None
    assert seed.entry_kind == "asset"
    assert seed.asset_type == "cash"
    assert seed.balance == 186543.22
    assert seed.as_of_date == date(2026, 3, 31)
    assert seed.position_key.startswith("account:")


def test_build_statement_snapshot_seed_for_credit_card_uses_total_due_as_liability():
    seed = build_statement_snapshot_seed(
        _statement(
            account_type="credit_card",
            account_number_masked="XX9988",
            closing_balance=None,
            total_amount_due=24567.89,
        )
    )

    assert seed is not None
    assert seed.entry_kind == "liability"
    assert seed.asset_type == "credit_card_due"
    assert seed.balance == 24567.89


def test_build_net_worth_history_carries_latest_position_values_forward():
    history = build_net_worth_history(
        [
            _snapshot("cash", date(2026, 1, 31), 1000),
            _snapshot("card", date(2026, 1, 31), 250, entry_kind="liability"),
            _snapshot("cash", date(2026, 2, 28), 1400),
            _snapshot("manual-gold", date(2026, 3, 31), 600),
        ],
        months=12,
    )

    assert history[0]["net_worth"] == 750.0
    assert history[1]["net_worth"] == 1150.0
    assert history[2]["assets"] == 2000.0
    assert history[2]["liabilities"] == 250.0
    assert history[2]["net_worth"] == 1750.0


def test_summarize_latest_positions_uses_latest_snapshot_per_position():
    positions, totals = summarize_latest_positions(
        [
            _snapshot("cash", date(2026, 1, 31), 1000),
            _snapshot("cash", date(2026, 2, 28), 1400),
            _snapshot("loan", date(2026, 2, 28), 300, entry_kind="liability"),
        ]
    )

    assert len(positions) == 2
    assert totals["assets"] == 1400.0
    assert totals["liabilities"] == 300.0
    assert totals["net_worth"] == 1100.0
