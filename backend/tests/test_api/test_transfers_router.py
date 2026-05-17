"""Smoke tests for transfers API contract — schema shape and resolution
state transitions. Uses stubbed DB; deeper integration belongs in
test_integration once that harness lands.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import transfers as transfers_api
from app.api.v1.transfers import (
    TransferResolutionRequest,
    _leg_from_canonical,
    _to_response,
)


def _canonical(direction: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        transaction_date=date(2026, 5, 1),
        amount="1500.00",
        bank_name="HDFC" if direction == "debit" else "ICICI",
        account_masked="XXXX1234" if direction == "debit" else "XXXX5678",
        direction=direction,
        merchant_raw="Transfer to savings",
        merchant_normalized="Transfer to savings",
    )


def _match(resolution: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        match_type="amount_date_window",
        confidence=0.92,
        resolution_status=resolution,
        matched_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        debit_transaction=_canonical("debit"),
        credit_transaction=_canonical("credit"),
    )


def test_leg_serializes_canonical_fields():
    canonical = _canonical("debit")
    leg = _leg_from_canonical(canonical)
    assert leg.transaction_id == str(canonical.id)
    assert leg.direction == "debit"
    assert leg.bank_name == "HDFC"
    assert leg.account_masked == "XXXX1234"
    assert leg.description == "Transfer to savings"


def test_to_response_includes_both_legs():
    match = _match("auto")
    response = _to_response(match)
    assert response.id == str(match.id)
    assert response.resolution_status == "auto"
    assert response.debit_leg.direction == "debit"
    assert response.credit_leg.direction == "credit"
    assert response.confidence == pytest.approx(0.92)


def test_resolution_request_accepts_only_known_decisions():
    confirmed = TransferResolutionRequest(decision="confirm")
    rejected = TransferResolutionRequest(decision="reject")
    assert confirmed.decision == "confirm"
    assert rejected.decision == "reject"
    with pytest.raises(Exception):
        TransferResolutionRequest(decision="maybe")  # type: ignore[arg-type]
