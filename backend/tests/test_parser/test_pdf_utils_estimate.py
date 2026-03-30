from __future__ import annotations

from app.engines.parser.pdf_utils import estimate_expected_transaction_rows


def test_estimate_expected_transaction_rows_uses_line_heuristic():
    pages = [
        "01/03/2026 UPI/DR/123 PHONEPE 850.00 12000.00\n"
        "02/03/2026 SALARY CREDIT 75000.00 87000.00\n"
        "Summary line without amount"
    ]
    # dummy bytes are fine because line fallback is used when table extraction fails.
    estimate = estimate_expected_transaction_rows(b"%PDF-1.4 invalid", pages=pages)
    assert estimate == 2

