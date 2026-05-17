from __future__ import annotations

from decimal import Decimal

from app.extraction.models import (
    ExtractionSource,
    RawTransaction,
)
from app.extraction.validator import (
    parse_decimal_amount,
    validate_transaction,
)


def _make_raw(**overrides) -> RawTransaction:
    values = {
        "date_raw": "15/04/2026",
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


def test_parse_decimal_amount_unsigned_positive() -> None:
    assert parse_decimal_amount("1,500.00") == Decimal("1500.00")
    assert parse_decimal_amount("₹2,34,567.89") == Decimal("234567.89")
    assert parse_decimal_amount("INR 100") == Decimal("100.00")


def test_parse_decimal_amount_signed_negative_via_parens() -> None:
    assert parse_decimal_amount("(500.00)", signed=True) == Decimal("-500.00")
    assert parse_decimal_amount("(1,234.56)", signed=True) == Decimal("-1234.56")


def test_parse_decimal_amount_unsigned_ignores_sign() -> None:
    result = parse_decimal_amount("(500.00)")
    assert result == Decimal("500.00")


def test_signed_balance_after_preserves_negative() -> None:
    result = validate_transaction(
        _make_raw(
            amount_raw="500.00",
            txn_type_raw="DR",
            balance_raw="(2,000.00)",
        )
    )
    assert result.balance_after == Decimal("-2000.00")
    assert "balance_negative" in result.validation_errors


def test_unsigned_balance_after_is_absolute() -> None:
    result = validate_transaction(
        _make_raw(
            amount_raw="500.00",
            txn_type_raw="DR",
            balance_raw="(2,000.00)",
        )
    )
    # balance_raw is parsed with signed=True internally in validate_transaction
    # but the original parse_decimal_amount call used signed=True
    assert result.balance_after == Decimal("-2000.00")


def test_parse_decimal_amount_parens_unsigned_returns_positive() -> None:
    result = parse_decimal_amount("(999.99)")
    assert result == Decimal("999.99")
