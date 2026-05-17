"""Anomaly detector — deterministic finding shape, sigma threshold, and
the new-large-merchant first-time rule."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.engines.insights.anomaly_detector import (
    AnomalyFinding,
    _category_spike,
    _new_large_merchant,
)


def _txn(
    *,
    amount: str,
    category_id: uuid.UUID | None = None,
    merchant_normalized: str | None = "Amazon",
    txn_date: date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        transaction_date=txn_date or date.today(),
        amount=Decimal(amount),
        merchant_normalized=merchant_normalized,
        merchant_raw=merchant_normalized or "Unknown",
        category_id=category_id,
        bank_name="HDFC",
    )


def test_category_spike_needs_minimum_history():
    cat = uuid.uuid4()
    txn = _txn(amount="900", category_id=cat)
    # Only 3 prior amounts → too noisy, no spike.
    finding = _category_spike(
        txn, "Food", Decimal("900"), [Decimal("100"), Decimal("110"), Decimal("105")], sigma=2.0
    )
    assert finding is None


def test_category_spike_fires_at_two_sigma():
    cat = uuid.uuid4()
    txn = _txn(amount="2000", category_id=cat)
    # Mean ≈ 100, stddev small — 2000 is many sigma away.
    history = [Decimal(str(amt)) for amt in [80, 100, 110, 95, 105, 90, 100, 115]]
    finding = _category_spike(txn, "Food", Decimal("2000"), history, sigma=2.0)
    assert finding is not None
    assert finding.reason == "category_spike"
    assert finding.deviation_ratio is not None
    assert finding.deviation_ratio > 2
    assert "Food" in finding.detail


def test_category_spike_silent_when_within_band():
    cat = uuid.uuid4()
    txn = _txn(amount="120", category_id=cat)
    history = [Decimal(str(amt)) for amt in [80, 100, 110, 95, 105, 90, 100, 115]]
    finding = _category_spike(txn, "Food", Decimal("120"), history, sigma=2.0)
    assert finding is None


def test_new_large_merchant_skips_below_floor():
    txn = _txn(amount="1000", merchant_normalized="NewBrand")
    finding = _new_large_merchant(
        txn, None, Decimal("1000"), {}, window_start=date.today() - timedelta(days=30),
        floor=Decimal("5000.00"),
    )
    assert finding is None


def test_new_large_merchant_fires_for_first_time_spend():
    txn = _txn(amount="9000", merchant_normalized="NewBrand")
    finding = _new_large_merchant(
        txn, "Shopping", Decimal("9000"), {"NEWBRAND": [date.today()]},
        window_start=date.today() - timedelta(days=30),
        floor=Decimal("5000.00"),
    )
    assert finding is not None
    assert finding.reason == "new_large_merchant"
    assert "NewBrand" in finding.detail


def test_new_large_merchant_silent_when_prior_history_outside_window():
    txn = _txn(amount="9000", merchant_normalized="RepeatBrand")
    window_start = date.today() - timedelta(days=30)
    history_dates = {"REPEATBRAND": [window_start - timedelta(days=10), date.today()]}
    finding = _new_large_merchant(
        txn, "Shopping", Decimal("9000"), history_dates,
        window_start=window_start,
        floor=Decimal("5000.00"),
    )
    assert finding is None


def test_anomaly_finding_to_dict_serializes_decimals_as_strings():
    finding = AnomalyFinding(
        transaction_id=uuid.uuid4(),
        transaction_date=date(2026, 5, 1),
        amount=Decimal("1234.56"),
        merchant="Test",
        category_id=None,
        category_name=None,
        bank_name="HDFC",
        reason="category_spike",
        detail="huge",
        expected_mean=Decimal("100.00"),
        expected_max=Decimal("250.00"),
        deviation_ratio=4.2,
    )
    payload = finding.to_dict()
    assert payload["amount"] == "1234.56"
    assert payload["expected_mean"] == "100.00"
    assert payload["expected_max"] == "250.00"
    assert payload["deviation_ratio"] == 4.2
    assert payload["transaction_date"] == "2026-05-01"
