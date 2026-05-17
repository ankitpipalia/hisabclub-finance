from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extraction.models import (
    ExtractionSource,
    RawTransaction,
    StatementPeriod,
    ValidationStatus,
)
from app.extraction.validator import validate_transaction


def make_raw(**overrides) -> RawTransaction:
    values = {
        "date_raw": date.today().strftime("%d/%m/%Y"),
        "description_raw": "UPI HDFC BANK",
        "amount_raw": "1,500.00",
        "balance_raw": None,
        "txn_type_raw": "DR",
        "page_number": 1,
        "char_offset": 20,
        "confidence": 0.95,
        "source": ExtractionSource.TEMPLATE,
        "source_evidence": {"line": "sample"},
    }
    values.update(overrides)
    return RawTransaction(**values)


def test_future_date_rejected() -> None:
    future = date.today() + timedelta(days=3)

    result = validate_transaction(make_raw(date_raw=future.strftime("%d/%m/%Y")))

    assert result.validation_status == ValidationStatus.INVALID
    assert "date_not_future" in result.validation_errors


def test_amount_normalisation_indian_format() -> None:
    result = validate_transaction(make_raw(amount_raw="1,00,000.50"))

    assert result.amount == Decimal("100000.50")


def test_cr_dr_ambiguous_flagged_for_review() -> None:
    result = validate_transaction(make_raw(txn_type_raw="NEFT"))

    assert result.validation_status == ValidationStatus.NEEDS_REVIEW
    assert "cr_dr_resolved" in result.validation_errors


def test_zero_amount_invalid() -> None:
    result = validate_transaction(make_raw(amount_raw="0.00"))

    assert result.validation_status == ValidationStatus.INVALID
    assert "amount_positive" in result.validation_errors


def test_date_outside_statement_period_needs_review() -> None:
    result = validate_transaction(
        make_raw(date_raw="01/01/2024"),
        statement_period=StatementPeriod(start=date(2024, 2, 1), end=date(2024, 2, 29)),
    )

    assert result.validation_status == ValidationStatus.NEEDS_REVIEW
    assert "date_within_statement_period" in result.validation_errors


@pytest.mark.parametrize("amount_str", ["₹1,500.00", "Rs.1500", "INR 1500.00", "1,500", "1500.5"])
def test_amount_formats_parsed(amount_str: str) -> None:
    result = validate_transaction(make_raw(amount_raw=amount_str))

    assert result.amount > 0


def test_more_than_two_decimal_places_invalid() -> None:
    result = validate_transaction(make_raw(amount_raw="1500.555"))

    assert result.validation_status == ValidationStatus.INVALID
    assert "amount_max_2_decimal" in result.validation_errors
