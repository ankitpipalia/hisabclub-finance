from __future__ import annotations

from app.engines.insights.statement_integrity import evaluate_credit_card_integrity


def test_integrity_ok_with_previous_balance() -> None:
    result = evaluate_credit_card_integrity(
        debit_total=5000.0,
        credit_total=1000.0,
        total_amount_due=4500.0,
        min_amount_due=None,
        previous_balance=0.0,
        closing_balance=4000.0,
        transaction_count=5,
    )
    assert result.status == "ok"
    assert result.due_gap is not None
    assert result.due_gap <= 500.0


def test_integrity_with_previous_balance_mismatch() -> None:
    result = evaluate_credit_card_integrity(
        debit_total=5000.0,
        credit_total=1000.0,
        total_amount_due=20000.0,
        min_amount_due=None,
        previous_balance=5000.0,
        closing_balance=4000.0,
        transaction_count=5,
    )
    # expected_due = 9000, gap = 11000 > tolerance 2000
    assert result.status == "review"


def test_integrity_review_when_no_transactions() -> None:
    result = evaluate_credit_card_integrity(
        debit_total=0.0,
        credit_total=0.0,
        total_amount_due=500.0,
        min_amount_due=250.0,
        previous_balance=0.0,
        closing_balance=0.0,
        transaction_count=0,
    )
    assert result.status == "review"


def test_integrity_balance_walk_passes() -> None:
    result = evaluate_credit_card_integrity(
        debit_total=3000.0,
        credit_total=500.0,
        total_amount_due=2500.0,
        min_amount_due=None,
        previous_balance=0.0,
        closing_balance=2500.0,
        transaction_count=3,
    )
    assert result.closing_balance_gap is not None
    assert result.closing_balance_gap <= 250.0
    assert result.status == "ok"
