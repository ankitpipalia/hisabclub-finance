import uuid
from datetime import date

from app.engines.ledger.fingerprint import (
    build_statement_semantic_fingerprint,
    build_transaction_dedupe_fingerprint,
)


def test_transaction_fingerprint_is_deterministic_and_stable() -> None:
    user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    first = build_transaction_dedupe_fingerprint(
        user_id=user_id,
        account_masked="XX1234",
        transaction_date=date(2026, 3, 1),
        amount=1000.0,
        description="UPI/Google Pay - BIG BAZAAR #9912",
    )
    second = build_transaction_dedupe_fingerprint(
        user_id=user_id,
        account_masked="xx1234",
        transaction_date=date(2026, 3, 1),
        amount=1000,
        description="upi google pay big bazaar 9912",
    )
    assert first == second
    assert len(first) == 64


def test_statement_semantic_fingerprint_requires_periods() -> None:
    fp = build_statement_semantic_fingerprint(
        user_id=uuid.uuid4(),
        institution_name="HDFC",
        account_masked="XX1234",
        period_start=None,
        period_end=date(2026, 3, 31),
        opening_balance=100.0,
    )
    assert fp is None


def test_statement_semantic_fingerprint_changes_when_period_changes() -> None:
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    fp_one = build_statement_semantic_fingerprint(
        user_id=user_id,
        institution_name="HDFC",
        account_masked="XX1234",
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        opening_balance=100.00,
    )
    fp_two = build_statement_semantic_fingerprint(
        user_id=user_id,
        institution_name="HDFC",
        account_masked="XX1234",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        opening_balance=100.00,
    )
    assert fp_one is not None
    assert fp_two is not None
    assert fp_one != fp_two
