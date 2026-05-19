"""Regression tests for the SMS batch import endpoint.

After Phase 1 (master_plan_2026.md §26) the legacy non-validated SMS path was
removed; every batch item runs through the typed extraction validator. These
tests guard that contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import sms as sms_api
from app.extraction.models import ValidationStatus
from app.schemas.sms import SmsBatchItemRequest, SmsBatchRequest


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _QueuedDb:
    def __init__(self, responses):
        self.responses = list(responses)
        self.added: list = []
        self.flush_count = 0
        self.commit_count = 0

    async def execute(self, *_args, **_kwargs):
        if not self.responses:
            return _ScalarOneOrNoneResult(None)
        return self.responses.pop(0)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1


def _valid_item(**overrides):
    payload = {
        "sms_hash": "h-" + uuid.uuid4().hex[:12],
        "sender_address": "AD-HDFCBK",
        "sender_id": "HDFCBK",
        "body": "INR 1,200.00 debited from a/c XXXX1234 on 21-04-25 at AMAZON. Avl bal INR 5,000.00",
        "sms_timestamp": datetime(2025, 4, 21, 13, 30, tzinfo=timezone.utc),
        "classification": "bank_transaction",
        "bank_name": "HDFC Bank",
        "account_type": "savings",
        "account_masked": "XXXX1234",
        "direction": "debit",
        "amount": 1200.00,
        "description": "AMAZON",
        "reference_number": None,
        "upi_id": None,
        "confidence": 0.92,
    }
    payload.update(overrides)
    return SmsBatchItemRequest(**payload)


@pytest.mark.asyncio
async def test_duplicate_sms_returns_duplicate_status_without_promotion(monkeypatch):
    """A second SMS with the same sms_hash for the same user is a no-op duplicate."""
    user = SimpleNamespace(id=uuid.uuid4())
    existing = SimpleNamespace(id=uuid.uuid4(), sms_hash="dup-hash")
    db = _QueuedDb([_ScalarOneOrNoneResult(existing)])

    promote_calls: list = []

    async def _no_promote(**kwargs):
        promote_calls.append(kwargs)
        raise AssertionError("promote_to_canonical must not be called for duplicates")

    monkeypatch.setattr(sms_api, "promote_to_canonical", _no_promote)

    request = SmsBatchRequest(items=[_valid_item(sms_hash="dup-hash")])

    response = await sms_api.sms_batch_import(request, user, db)

    assert response.duplicates == 1
    assert response.accepted == 0
    assert response.errors == 0
    assert response.details[0].status == "duplicate"
    assert promote_calls == []


@pytest.mark.asyncio
async def test_invalid_amount_returns_error_and_does_not_promote(monkeypatch):
    """An item whose typed validation fails (INVALID) is reported as an error, never promoted."""
    user = SimpleNamespace(id=uuid.uuid4())
    db = _QueuedDb([_ScalarOneOrNoneResult(None)])

    promote_calls: list = []

    async def _spy_promote(**kwargs):
        promote_calls.append(kwargs)
        raise AssertionError("promote_to_canonical must not be called for INVALID items")

    monkeypatch.setattr(sms_api, "promote_to_canonical", _spy_promote)

    # amount=0 is rejected by validate_transaction as INVALID; this is the
    # critical contract: even with the typed-validation flag flipped on, this
    # row must not become canonical.
    bad = _valid_item(amount=0)
    request = SmsBatchRequest(items=[bad])

    response = await sms_api.sms_batch_import(request, user, db)

    assert response.errors == 1
    assert response.accepted == 0
    assert response.details[0].status == "error"
    assert promote_calls == []


@pytest.mark.asyncio
async def test_low_confidence_promotes_with_review_task(monkeypatch):
    """LOW_CONFIDENCE rows still promote, but with quarantined=True + a review task."""
    user = SimpleNamespace(id=uuid.uuid4())
    db = _QueuedDb([_ScalarOneOrNoneResult(None)])

    promote_calls: list = []
    review_calls: list = []

    canonical_stub = SimpleNamespace(id=uuid.uuid4())

    async def _spy_promote(**kwargs):
        promote_calls.append(kwargs)
        return canonical_stub

    async def _spy_review(*args, **kwargs):
        review_calls.append((args, kwargs))

    monkeypatch.setattr(sms_api, "promote_to_canonical", _spy_promote)
    monkeypatch.setattr(sms_api, "create_review_task_for_canonical", _spy_review)

    # confidence < 0.75 forces validator into LOW_CONFIDENCE territory.
    request = SmsBatchRequest(items=[_valid_item(confidence=0.40)])

    response = await sms_api.sms_batch_import(request, user, db)

    assert response.accepted == 1
    assert response.errors == 0

    assert len(promote_calls) == 1
    promote_kwargs = promote_calls[0]
    # validation_status must be passed through (not silently coerced to "valid")
    assert promote_kwargs["validation_status"] in {
        ValidationStatus.LOW_CONFIDENCE.value,
        ValidationStatus.NEEDS_REVIEW.value,
    }
    assert promote_kwargs["parsed_txn"].is_quarantined is True

    assert len(review_calls) == 1, "Low-confidence SMS must create a review task"
