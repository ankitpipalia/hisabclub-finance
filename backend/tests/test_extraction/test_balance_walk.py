from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extraction.models import (
    ExtractionSource,
    RawTransaction,
    ValidatedTransaction,
    ValidationStatus,
)
from app.extraction.validator import balance_walk_check


def make_txn(
    amount: str | Decimal,
    *,
    is_credit: bool,
    balance_after: Decimal | None = None,
    txn_date: date = date(2026, 4, 1),
    description: str = "sample",
) -> ValidatedTransaction:
    raw = RawTransaction(
        date_raw=txn_date.strftime("%d/%m/%Y"),
        description_raw=description,
        amount_raw=str(amount),
        balance_raw=str(balance_after) if balance_after is not None else None,
        txn_type_raw="CR" if is_credit else "DR",
        page_number=1,
        char_offset=0,
        confidence=1.0,
        source=ExtractionSource.TEMPLATE,
        source_evidence={},
    )
    return ValidatedTransaction(
        txn_date=txn_date,
        description=description,
        amount=Decimal(str(amount)),
        is_credit=is_credit,
        balance_after=balance_after,
        category_hint=None,
        raw=raw,
        validation_status=ValidationStatus.VALID,
    )


def test_perfect_statement_passes() -> None:
    txns = [
        make_txn("1000", is_credit=True, balance_after=Decimal("11000")),
        make_txn("500", is_credit=False, balance_after=Decimal("10500")),
    ]

    result = balance_walk_check(txns, Decimal("10000"), Decimal("10500"))

    assert result.passed
    assert result.delta == Decimal("0")


def test_one_rupee_tolerance() -> None:
    txns = [make_txn("333.33", is_credit=True)]

    result = balance_walk_check(txns, Decimal("10000"), Decimal("10333.34"))

    assert result.passed


def test_missing_transaction_detected() -> None:
    txns = [make_txn("100", is_credit=True)]

    result = balance_walk_check(txns, Decimal("10000"), Decimal("10500"))

    assert not result.passed
    assert result.delta == Decimal("400")


def test_empty_statement() -> None:
    result = balance_walk_check([], Decimal("10000"), Decimal("10000"))

    assert result.passed


def test_problematic_txn_identified() -> None:
    txns = [
        make_txn("100", is_credit=True, balance_after=Decimal("10100")),
        make_txn("100", is_credit=True, balance_after=Decimal("10300")),
    ]

    result = balance_walk_check(txns, Decimal("10000"), Decimal("10300"))

    assert [problem.index_in_input for problem in result.problematic_txns] == [1]
    assert result.problematic_txns[0].description_prefix == "sample"


def test_problematic_txn_identifier_survives_date_sorting() -> None:
    txns = [
        make_txn(
            "100",
            is_credit=True,
            balance_after=Decimal("10300"),
            txn_date=date(2026, 4, 2),
            description="later problematic",
        ),
        make_txn(
            "100",
            is_credit=True,
            balance_after=Decimal("10100"),
            txn_date=date(2026, 4, 1),
            description="first ok",
        ),
    ]

    result = balance_walk_check(txns, Decimal("10000"), Decimal("10300"))

    assert [problem.index_in_input for problem in result.problematic_txns] == [0]
    assert result.problematic_txns[0].txn_date == date(2026, 4, 2)
    assert result.problematic_txns[0].description_prefix == "later problematic"
