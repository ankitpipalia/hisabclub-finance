from __future__ import annotations

from datetime import date

from app.engines.parser.base import ExtractedStatement, ExtractedTransaction
from app.engines.parser.validation import validate_extracted_statement


def test_validate_extracted_statement_balance_walk_ok_for_savings() -> None:
    statement = ExtractedStatement(
        bank_name="SBI",
        account_type="savings",
        opening_balance=1000.0,
        closing_balance=1300.0,
        transactions=[
            ExtractedTransaction(
                transaction_date=date(2025, 4, 2),
                posting_date=None,
                description="SALARY",
                amount=500.0,
                direction="credit",
            ),
            ExtractedTransaction(
                transaction_date=date(2025, 4, 4),
                posting_date=None,
                description="UPI PAYMENT",
                amount=200.0,
                direction="debit",
            ),
        ],
    )

    result = validate_extracted_statement(statement)

    assert result.review_required is False
    assert result.details["balance_walk"]["ok"] is True
    assert result.details["balance_walk"]["gap"] == 0.0


def test_validate_extracted_statement_balance_walk_flags_review() -> None:
    statement = ExtractedStatement(
        bank_name="ICICI",
        account_type="savings",
        opening_balance=1000.0,
        closing_balance=1800.0,
        transactions=[
            ExtractedTransaction(
                transaction_date=date(2025, 4, 2),
                posting_date=None,
                description="SALARY",
                amount=500.0,
                direction="credit",
            ),
            ExtractedTransaction(
                transaction_date=date(2025, 4, 4),
                posting_date=None,
                description="UPI PAYMENT",
                amount=200.0,
                direction="debit",
            ),
        ],
    )

    result = validate_extracted_statement(statement)

    assert result.review_required is True
    assert result.details["balance_walk"]["ok"] is False
    assert result.details["balance_walk"]["gap"] == 500.0


def test_balance_walk_strict_tolerance() -> None:
    statement = ExtractedStatement(
        bank_name="HDFC",
        account_type="savings",
        opening_balance=1000.0,
        closing_balance=1000.5,
        transactions=[
            ExtractedTransaction(
                transaction_date=date(2025, 4, 2),
                posting_date=None,
                description="SALARY",
                amount=500.0,
                direction="credit",
            ),
            ExtractedTransaction(
                transaction_date=date(2025, 4, 4),
                posting_date=None,
                description="ATM",
                amount=500.0,
                direction="debit",
            ),
        ],
    )

    result = validate_extracted_statement(statement)

    assert result.details["balance_walk"]["ok"] is True
    assert result.details["balance_walk"]["gap"] == 0.5
    assert result.details["balance_walk"]["tolerance"] == 1.0
