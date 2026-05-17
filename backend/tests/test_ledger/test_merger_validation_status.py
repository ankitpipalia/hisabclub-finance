from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.engines.ledger.merger import promote_to_canonical
from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.transaction_source import TransactionSource


class _FakeDb:
    def __init__(self):
        self.added = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)

    async def flush(self):
        return None


def _parsed() -> ParsedTransaction:
    return ParsedTransaction(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        source_type="sms",
        source_id=uuid.uuid4(),
        transaction_date=date(2024, 1, 5),
        description_raw="UPI TEST",
        amount=Decimal("100.00"),
        direction="debit",
        currency="INR",
        confidence=0.5,
        extraction_method="sms_regex",
    )


@pytest.fixture(autouse=True)
def _patch_dependencies(monkeypatch):
    async def _no_duplicate(*_args, **_kwargs):
        return None, 0.0, ""

    async def _normalize(_db, _description):
        return None, None, "UPI TEST"

    async def _infer(**_kwargs):
        return None, "auto"

    monkeypatch.setattr("app.engines.ledger.merger._dedup_engine.find_duplicate", _no_duplicate)
    monkeypatch.setattr("app.engines.ledger.merger.normalize_and_categorize", _normalize)
    monkeypatch.setattr("app.engines.ledger.merger.infer_uncategorized_category", _infer)


@pytest.mark.asyncio
async def test_promote_to_canonical_preserves_default_validation_status():
    db = _FakeDb()
    parsed = _parsed()

    canonical = await promote_to_canonical(
        db=db,
        user_id=parsed.user_id,
        parsed_txn=parsed,
        bank_name="HDFC",
        account_type="savings",
        account_masked="XX1234",
    )

    assert canonical.validation_status == "valid"
    assert canonical.validation_errors is None
    assert canonical.balance_walk_passed is None
    assert getattr(canonical, "_hc_was_dedup_merge") is False
    assert any(isinstance(obj, TransactionSource) for obj in db.added)


@pytest.mark.asyncio
async def test_promote_to_canonical_propagates_validation_audit_fields():
    db = _FakeDb()
    parsed = _parsed()

    canonical = await promote_to_canonical(
        db=db,
        user_id=parsed.user_id,
        parsed_txn=parsed,
        bank_name="HDFC",
        account_type="savings",
        account_masked="XX1234",
        validation_status="needs_review",
        validation_errors=["cr_dr_resolved"],
        balance_walk_passed=False,
    )

    assert isinstance(canonical, CanonicalTransaction)
    assert canonical.validation_status == "needs_review"
    assert canonical.validation_errors == ["cr_dr_resolved"]
    assert canonical.balance_walk_passed is False
