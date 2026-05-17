from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.engines.parser.templates.bob_savings import (
    extract_meta,
    extract_transactions,
    parse_amount,
    parse_date_str,
    to_raw_transaction,
)
from app.extraction.models import ExtractionSource, StatementPeriod, ValidationStatus
from app.extraction.validator import balance_walk_check, validate_transaction


class TestParseHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1,00,000.50", Decimal("100000.50")),
            ("5,000", Decimal("5000")),
            ("340.00", Decimal("340.00")),
            ("", None),
            ("N/A", None),
        ],
    )
    def test_parse_amount(self, value, expected):
        assert parse_amount(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("01/04/2024", date(2024, 4, 1)),
            ("31-03-2025", date(2025, 3, 31)),
            ("15-Apr-2024", date(2024, 4, 15)),
            ("garbage", None),
        ],
    )
    def test_parse_date(self, value, expected):
        assert parse_date_str(value) == expected


@pytest.fixture
def bob_pages_text():
    return [
        """
BANK OF BARODA
Account Number: 1234 5678 9012
Statement Period: 01/04/2024 to 31/03/2025
Opening Balance: 10,000.00
TRAN DATE VALUE DATE NARRATION CHQ.NO. WITHDRAWAL(DR) DEPOSIT(CR) BALANCE(INR)
01/04/2024 01/04/2024 NEFT CR SALARY APRIL NEFT12345 50,000.00 60,000.00Cr
05/04/2024 05/04/2024 UPI SWIGGY ORDER UPI98765 340.00 59,660.00Cr
10/04/2024 10/04/2024 ATM WDL HDFC BANK ATM11111 5,000.00 54,660.00Cr
30/04/2024 30/04/2024 INTEREST CREDIT INT99999 312.50 54,972.50Cr
Closing Balance: 54,972.50
"""
    ]


class TestBOBExtraction:
    def test_meta_extracted(self, bob_pages_text):
        meta = extract_meta("\n".join(bob_pages_text))
        assert meta.period_start == date(2024, 4, 1)
        assert meta.period_end == date(2025, 3, 31)
        assert meta.opening_balance == Decimal("10000.00")
        assert meta.closing_balance == Decimal("54972.50")

    def test_four_transactions_extracted(self, bob_pages_text):
        assert len(extract_transactions(bob_pages_text)) == 4

    def test_cr_dr_directions_correct(self, bob_pages_text):
        raw = [to_raw_transaction(row) for row in extract_transactions(bob_pages_text)]
        assert [txn.txn_type_raw for txn in raw] == ["CR", "DR", "DR", "CR"]

    def test_no_llm_source(self, bob_pages_text):
        raw = [to_raw_transaction(row) for row in extract_transactions(bob_pages_text)]
        assert all(txn.source == ExtractionSource.TEMPLATE for txn in raw)

    def test_all_high_confidence(self, bob_pages_text):
        raw = [to_raw_transaction(row) for row in extract_transactions(bob_pages_text)]
        assert all(txn.confidence >= 0.9 for txn in raw)

    def test_balance_walk_passes(self, bob_pages_text):
        full_text = "\n".join(bob_pages_text)
        meta = extract_meta(full_text)
        raw = [to_raw_transaction(row) for row in extract_transactions(bob_pages_text)]
        period = StatementPeriod(start=meta.period_start, end=meta.period_end)
        valid = [validate_transaction(txn, statement_period=period) for txn in raw]
        valid = [txn for txn in valid if txn.validation_status != ValidationStatus.INVALID]

        result = balance_walk_check(valid, meta.opening_balance, meta.closing_balance)

        assert result.passed, f"Balance walk FAILED: delta=Rs {result.delta}"
        assert result.delta == Decimal("0.00")

    def test_source_evidence_complete(self, bob_pages_text):
        raw = [to_raw_transaction(row) for row in extract_transactions(bob_pages_text)]
        for txn in raw:
            assert "narration" in txn.source_evidence
            assert "ref_number" in txn.source_evidence

    @pytest.mark.skipif(
        not Path("/home/ankit/Documents/FY24-25-Ankit-details/BOB/0206-statement.pdf").exists(),
        reason="Real documents not available in CI",
    )
    def test_real_bob_statement(self):
        import pdfplumber

        bob_path = Path("/home/ankit/Documents/FY24-25-Ankit-details/BOB/0206-statement.pdf")
        with pdfplumber.open(str(bob_path)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
        full_text = "\n".join(pages_text)

        meta = extract_meta(full_text)
        rows = extract_transactions(pages_text)
        raw = [to_raw_transaction(row) for row in rows]

        assert meta.period_start is not None
        assert meta.period_end is not None
        assert meta.opening_balance is not None
        assert meta.closing_balance is not None
        assert len(rows) >= 1
        assert {txn.txn_type_raw for txn in raw} >= {"CR", "DR"}
        assert {txn.source for txn in raw} == {ExtractionSource.TEMPLATE}

        period = StatementPeriod(start=meta.period_start, end=meta.period_end)
        valid = [validate_transaction(txn, statement_period=period) for txn in raw]
        result = balance_walk_check(valid, meta.opening_balance, meta.closing_balance)
        assert result.passed, f"Balance walk FAILED: delta=Rs {result.delta}"
