"""Tests for SMS↔statement matching engine (Sprint C.6)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.engines.ledger.sms_statement_match import (
    _AMOUNT_TOLERANCE,
    match_sms_to_statements,
)


def _canonical(
    *,
    extraction_source: str,
    amount: str,
    txn_date: date,
    account_masked: str = "XX1234",
    direction: str = "debit",
    parsed_txn_id: uuid.UUID | None = None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        parsed_txn_id=parsed_txn_id or uuid.uuid4(),
        amount=Decimal(amount),
        transaction_date=txn_date,
        account_masked=account_masked,
        direction=direction,
        extraction_source=extraction_source,
        is_excluded=False,
        source_evidence={},
    )


class _ScalarsAllResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return self._items


class _ListExecResult:
    def __init__(self, items):
        self._items = list(items)

    def first(self):
        return self._items[0] if self._items else None

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


class _Db:
    def __init__(self, canonicals):
        self.canonicals = canonicals
        self.added = []
        self.flush_count = 0
        # The matcher's first execute() returns the canonical pool; subsequent
        # ones load the SMS ParsedTransaction source and check existing links.
        self._first_call = True
        self._post_pool_calls = 0

    async def execute(self, *_args, **_kwargs):
        if self._first_call:
            self._first_call = False
            return _ScalarsAllResult(self.canonicals)
        self._post_pool_calls += 1
        if self._post_pool_calls % 2 == 1:
            sms = next(
                (
                    row for row in self.canonicals
                    if getattr(row, "extraction_source", "") == "sms"
                ),
                None,
            )
            return _ListExecResult([sms.parsed_txn_id] if sms else [])
        return _ListExecResult([])

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_sms_matches_statement_within_3_days_and_amount_tolerance():
    sms = _canonical(
        extraction_source="sms",
        amount="1200.00",
        txn_date=date(2024, 5, 10),
    )
    statement = _canonical(
        extraction_source="template",
        amount="1200.50",  # within tolerance
        txn_date=date(2024, 5, 11),  # 1 day gap
    )
    db = _Db([sms, statement])
    report = await match_sms_to_statements(db, user_id=uuid.uuid4(), fy=None)

    assert report.matched_pairs == 1
    assert report.sms_unmatched == 0
    assert report.matches[0].sms_canonical_id == sms.id
    assert report.matches[0].statement_canonical_id == statement.id
    assert report.matches[0].date_gap_days == 1
    assert db.added[0].parsed_txn_id == sms.parsed_txn_id


@pytest.mark.asyncio
async def test_sms_rejected_when_amount_diff_exceeds_tolerance():
    sms = _canonical(extraction_source="sms", amount="1200.00", txn_date=date(2024, 5, 10))
    statement = _canonical(
        extraction_source="template",
        amount="1300.00",  # outside _AMOUNT_TOLERANCE
        txn_date=date(2024, 5, 10),
    )
    db = _Db([sms, statement])
    report = await match_sms_to_statements(db, user_id=uuid.uuid4(), fy=None)
    assert report.matched_pairs == 0
    assert report.sms_unmatched == 1


@pytest.mark.asyncio
async def test_sms_rejected_when_date_outside_window():
    sms = _canonical(extraction_source="sms", amount="1200.00", txn_date=date(2024, 5, 10))
    statement = _canonical(
        extraction_source="template",
        amount="1200.00",
        txn_date=date(2024, 5, 20),  # 10-day gap
    )
    db = _Db([sms, statement])
    report = await match_sms_to_statements(db, user_id=uuid.uuid4(), fy=None)
    assert report.matched_pairs == 0


@pytest.mark.asyncio
async def test_sms_rejected_when_direction_mismatch():
    sms = _canonical(
        extraction_source="sms", amount="1200.00", txn_date=date(2024, 5, 10), direction="debit"
    )
    statement = _canonical(
        extraction_source="template",
        amount="1200.00",
        txn_date=date(2024, 5, 10),
        direction="credit",
    )
    db = _Db([sms, statement])
    report = await match_sms_to_statements(db, user_id=uuid.uuid4(), fy=None)
    assert report.matched_pairs == 0


@pytest.mark.asyncio
async def test_sms_rejected_when_account_mismatch():
    sms = _canonical(
        extraction_source="sms",
        amount="1200.00",
        txn_date=date(2024, 5, 10),
        account_masked="XX1234",
    )
    statement = _canonical(
        extraction_source="template",
        amount="1200.00",
        txn_date=date(2024, 5, 10),
        account_masked="XX9999",
    )
    db = _Db([sms, statement])
    report = await match_sms_to_statements(db, user_id=uuid.uuid4(), fy=None)
    assert report.matched_pairs == 0


@pytest.mark.asyncio
async def test_prefers_smaller_date_gap_over_first_match():
    sms = _canonical(extraction_source="sms", amount="1200.00", txn_date=date(2024, 5, 10))
    far_statement = _canonical(
        extraction_source="template", amount="1200.00", txn_date=date(2024, 5, 13)
    )
    near_statement = _canonical(
        extraction_source="template", amount="1200.00", txn_date=date(2024, 5, 11)
    )
    db = _Db([sms, far_statement, near_statement])
    report = await match_sms_to_statements(db, user_id=uuid.uuid4(), fy=None)
    assert report.matched_pairs == 1
    assert report.matches[0].statement_canonical_id == near_statement.id
    assert report.matches[0].date_gap_days == 1


def test_amount_tolerance_constant():
    """Lock in the published tolerance so accidental edits trip a test."""
    assert _AMOUNT_TOLERANCE == Decimal("1.00")
