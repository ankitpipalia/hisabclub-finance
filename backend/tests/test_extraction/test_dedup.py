from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engines.ledger.dedup import _quantized_amount
from app.extraction.models import (
    ExtractionSource,
    RawTransaction,
    ValidatedTransaction,
    ValidationStatus,
)
from app.extraction.validator import dedup_key


def make_validated(
    *,
    description: str = "UPI/HDFC BANK",
    amount: Decimal = Decimal("100.00"),
    is_credit: bool = False,
) -> ValidatedTransaction:
    raw = RawTransaction(
        date_raw="01/04/2026",
        description_raw=description,
        amount_raw=str(amount),
        balance_raw=None,
        txn_type_raw="CR" if is_credit else "DR",
        page_number=1,
        char_offset=0,
        confidence=1.0,
        source=ExtractionSource.TEMPLATE,
        source_evidence={},
    )
    return ValidatedTransaction(
        txn_date=date(2026, 4, 1),
        description=description,
        amount=amount,
        is_credit=is_credit,
        balance_after=None,
        category_hint=None,
        raw=raw,
        validation_status=ValidationStatus.VALID,
    )


def test_same_import_produces_same_key() -> None:
    txn = make_validated()

    assert dedup_key(1, txn) == dedup_key(1, txn)


def test_different_account_different_key() -> None:
    txn = make_validated()

    assert dedup_key(1, txn) != dedup_key(2, txn)


def test_description_whitespace_normalised() -> None:
    txn_a = make_validated(description="UPI/HDFC  BANK")
    txn_b = make_validated(description="UPI/HDFC BANK")

    assert dedup_key(1, txn_a) == dedup_key(1, txn_b)


def test_one_paise_difference_different_key() -> None:
    txn_a = make_validated(amount=Decimal("100.00"))
    txn_b = make_validated(amount=Decimal("100.01"))

    assert dedup_key(1, txn_a) != dedup_key(1, txn_b)


def test_credit_and_debit_have_different_keys() -> None:
    txn_a = make_validated(is_credit=False)
    txn_b = make_validated(is_credit=True)

    assert dedup_key(1, txn_a) != dedup_key(1, txn_b)


def test_sql_dedup_amount_quantization_avoids_float_boundary() -> None:
    value = Decimal("0.1") + Decimal("0.2")

    assert _quantized_amount(value) == Decimal("0.30")
    assert _quantized_amount("100.005") == Decimal("100.01")
