from app.engines.parser.base import _ensure_parsers_loaded, detect_parser


def _hdfc_cc_like_text() -> str:
    return """
HDFC Bank Credit Card Statement
Account Statement for March 2026
Transaction: CREDIT CARD PAYMENT TO HDFC BANK
"""


def test_detect_parser_strict_hints_reject_mismatched_bank_and_type():
    _ensure_parsers_loaded()
    parser = detect_parser(
        _hdfc_cc_like_text(),
        bank_hint="ICICI",
        account_type_hint="bank_account",
        strict_bank_hint=True,
        strict_account_type_hint=True,
    )
    assert parser is None


def test_detect_parser_non_strict_can_fallback_to_detected_candidate():
    _ensure_parsers_loaded()
    parser = detect_parser(
        _hdfc_cc_like_text(),
        bank_hint="ICICI",
        account_type_hint="bank_account",
        strict_bank_hint=False,
        strict_account_type_hint=False,
    )
    assert parser is not None
    assert parser.parser_id == "hdfc_cc_v1"
