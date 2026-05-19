from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from app.extraction.models import (
    ExtractionSource,
    RawTransaction,
    StatementPeriod,
    ValidationStatus,
)
from app.extraction.promoter import promote_validated_batch
from app.models.canonical_transaction import CanonicalTransaction
from app.models.review_task import ReviewTask


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeDb:
    def __init__(self):
        self.added = []
        self.existing_keys = set()
        self.flush_count = 0

    async def execute(self, *_args, **_kwargs):
        return _Rows([(key,) for key in self.existing_keys])

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if isinstance(obj, CanonicalTransaction) and obj.dedup_key:
            self.existing_keys.add(obj.dedup_key)
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


def _raw(
    *,
    amount="100.00",
    txn_type="DR",
    confidence=0.95,
    description="UPI/SWIGGY ORDER",
    source=ExtractionSource.TEMPLATE,
):
    return RawTransaction(
        date_raw="05/01/2024",
        description_raw=description,
        amount_raw=amount,
        balance_raw=None,
        txn_type_raw=txn_type,
        page_number=1,
        char_offset=10,
        confidence=confidence,
        source=source,
        source_evidence={"description": description, "amount": amount},
    )


@pytest.fixture(autouse=True)
def _disable_external_enrichment(monkeypatch):
    async def _normalize(_db, _description):
        return None, None, "Normalized Merchant"

    async def _infer(**_kwargs):
        return None, "auto"

    async def _no_reimport_signatures(**_kwargs):
        return set()

    monkeypatch.setattr("app.extraction.promoter._normalize_and_categorize", _normalize)
    monkeypatch.setattr("app.extraction.promoter._infer_uncategorized_category", _infer)
    monkeypatch.setattr(
        "app.extraction.promoter._fetch_existing_reimport_signatures",
        _no_reimport_signatures,
    )


@pytest.mark.asyncio
async def test_promoter_inserts_audited_canonical_transaction():
    db = _FakeDb()
    user_id = uuid.uuid4()
    statement_id = uuid.uuid4()

    result = await promote_validated_batch(
        raw_txns=[_raw()],
        user_id=user_id,
        account_id=uuid.uuid4(),
        statement_id=statement_id,
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=Decimal("1000.00"),
        closing_balance=Decimal("900.00"),
        bank_name="HDFC",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    canonical = next(obj for obj in db.added if isinstance(obj, CanonicalTransaction))
    assert len(result.promoted) == 1
    assert result.duplicates == 0
    assert canonical.dedup_key
    assert canonical.source_statement_id == statement_id
    assert canonical.source_page_number == 1
    assert canonical.source_evidence is not None
    assert canonical.validation_status == "valid"
    assert canonical.balance_walk_passed is True


@pytest.mark.asyncio
async def test_promoter_reimport_counts_duplicate_without_insert():
    db = _FakeDb()
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    statement_id = uuid.uuid4()
    kwargs = dict(
        raw_txns=[_raw()],
        user_id=user_id,
        account_id=account_id,
        statement_id=statement_id,
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=Decimal("1000.00"),
        closing_balance=Decimal("900.00"),
        bank_name="HDFC",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    first = await promote_validated_batch(**kwargs)
    second = await promote_validated_batch(**kwargs)

    assert len(first.promoted) == 1
    assert len(second.promoted) == 0
    assert second.duplicates == 1


@pytest.mark.asyncio
async def test_reimport_signature_catches_llm_direction_flip(monkeypatch):
    db = _FakeDb()
    user_id = uuid.uuid4()
    account_masked = "XX1234"

    from app.extraction.promoter import _reimport_transaction_signature

    existing_signature = _reimport_transaction_signature(
        transaction_date=date(2024, 1, 5),
        amount=Decimal("100.00"),
        description="PPF-E-PAY",
    )

    async def _existing_reimport_signatures(**_kwargs):
        return {existing_signature}

    monkeypatch.setattr(
        "app.extraction.promoter._fetch_existing_reimport_signatures",
        _existing_reimport_signatures,
    )

    result = await promote_validated_batch(
        raw_txns=[_raw(txn_type="DR", description="PPF-E-PAY")],
        user_id=user_id,
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=None,
        closing_balance=None,
        bank_name="BOB",
        account_type="savings",
        account_masked=account_masked,
        db=db,
    )

    assert result.duplicates == 1
    assert len(result.promoted) == 0


@pytest.mark.asyncio
async def test_low_confidence_ai_sourced_transaction_gets_review_task():
    db = _FakeDb()
    result = await promote_validated_batch(
        raw_txns=[_raw(confidence=0.5, source=ExtractionSource.LLM_TEXT)],
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=None,
        closing_balance=None,
        bank_name="HDFC",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    reviews = [obj for obj in db.added if isinstance(obj, ReviewTask)]
    assert len(result.queued_for_review) == 1
    assert len(reviews) == 1
    assert "low_confidence" in reviews[0].payload_json["reasons"]
    assert "ai_sourced" in reviews[0].payload_json["reasons"]


@pytest.mark.asyncio
async def test_large_template_transaction_with_passing_balance_walk_does_not_queue_review():
    db = _FakeDb()
    result = await promote_validated_batch(
        raw_txns=[_raw(amount="150000.00", confidence=0.98, source=ExtractionSource.TEMPLATE)],
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=Decimal("200000.00"),
        closing_balance=Decimal("50000.00"),
        bank_name="BOB",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    assert result.balance_walk_passed is True
    assert len(result.promoted) == 1
    assert result.queued_for_review == []
    assert not [obj for obj in db.added if isinstance(obj, ReviewTask)]


@pytest.mark.asyncio
async def test_large_ai_transaction_without_balance_walk_still_gets_review_task():
    db = _FakeDb()
    result = await promote_validated_batch(
        raw_txns=[_raw(amount="150000.00", confidence=0.98, source=ExtractionSource.LLM_TEXT)],
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=None,
        closing_balance=None,
        bank_name="UNKNOWN",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    reviews = [obj for obj in db.added if isinstance(obj, ReviewTask)]
    assert len(result.queued_for_review) == 1
    assert len(reviews) == 1
    assert "ai_sourced" in reviews[0].payload_json["reasons"]
    assert "large_amount" in reviews[0].payload_json["reasons"]


@pytest.mark.asyncio
async def test_ambiguous_direction_promotes_as_reviewable_debit_by_default():
    """Phase 1: `extraction_review_keeps_ambiguous_direction` default is now True,
    so ambiguous CR/DR rows route to review (with assumed debit + cr_dr_resolved
    flag) instead of being silently dropped. No flag override required."""
    db = _FakeDb()
    result = await promote_validated_batch(
        raw_txns=[_raw(txn_type="NEFT", description="NEFT TRANSFER")],
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=None,
        closing_balance=None,
        bank_name="BOB",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    canonical = next(obj for obj in db.added if isinstance(obj, CanonicalTransaction))
    reviews = [obj for obj in db.added if isinstance(obj, ReviewTask)]
    assert len(result.promoted) == 1
    assert canonical.direction == "debit"
    assert canonical.validation_status == ValidationStatus.NEEDS_REVIEW.value
    assert "cr_dr_resolved" in canonical.validation_errors
    assert len(reviews) == 1
    assert "needs_review" in reviews[0].payload_json["reasons"]


@pytest.mark.asyncio
async def test_ambiguous_direction_promotes_as_reviewable_debit_when_flag_enabled(monkeypatch):
    monkeypatch.setattr(
        "app.extraction.promoter.settings.extraction_review_keeps_ambiguous_direction",
        True,
    )
    db = _FakeDb()
    result = await promote_validated_batch(
        raw_txns=[_raw(txn_type="NEFT", description="NEFT TRANSFER")],
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=StatementPeriod(date(2024, 1, 1), date(2024, 1, 31)),
        opening_balance=None,
        closing_balance=None,
        bank_name="BOB",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    canonical = next(obj for obj in db.added if isinstance(obj, CanonicalTransaction))
    reviews = [obj for obj in db.added if isinstance(obj, ReviewTask)]
    assert len(result.promoted) == 1
    assert canonical.direction == "debit"
    assert canonical.validation_status == ValidationStatus.NEEDS_REVIEW.value
    assert "cr_dr_resolved" in canonical.validation_errors
    assert len(reviews) == 1
    assert "needs_review" in reviews[0].payload_json["reasons"]


@pytest.mark.asyncio
async def test_invalid_future_transaction_is_skipped():
    db = _FakeDb()
    result = await promote_validated_batch(
        raw_txns=[RawTransaction(
            date_raw="31/12/2099",
            description_raw="BAD FUTURE",
            amount_raw="10.00",
            balance_raw=None,
            txn_type_raw="DR",
            page_number=1,
            char_offset=0,
            confidence=0.9,
            source=ExtractionSource.TEMPLATE,
            source_evidence={},
        )],
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        statement_period=None,
        opening_balance=None,
        closing_balance=None,
        bank_name="HDFC",
        account_type="savings",
        account_masked="XX1234",
        db=db,
    )

    assert result.invalid == 1
    assert not [obj for obj in db.added if isinstance(obj, CanonicalTransaction)]
