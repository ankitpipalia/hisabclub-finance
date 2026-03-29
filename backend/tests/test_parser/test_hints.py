from app.engines.parser.hints import (
    infer_account_type_hint_from_text,
    infer_bank_hint_from_text,
    normalize_account_type_hint,
    normalize_bank_hint,
    normalize_parser_hints,
)


def test_normalize_bank_hint_handles_extended_bank_aliases():
    assert normalize_bank_hint("State Bank of India") == "SBI"
    assert normalize_bank_hint("HDFC Bank") == "HDFC"
    assert normalize_bank_hint("Punjab National Bank") == "PNB"
    assert normalize_bank_hint("IndusInd Bank") == "INDUSIND"
    assert normalize_bank_hint("Federal Bank") == "FEDERAL"


def test_normalize_account_type_hint_handles_auto_and_bank_account():
    assert normalize_account_type_hint("auto") == "auto"
    assert normalize_account_type_hint("bank account") == "bank_account"
    assert normalize_account_type_hint("credit_card") == "credit_card"
    assert normalize_account_type_hint("savings") == "bank_account"


def test_normalize_parser_hints_combines_values():
    hints = normalize_parser_hints("Kotak Mahindra Bank", "credit card")
    assert hints.bank_hint == "KOTAK"
    assert hints.account_type_hint == "credit_card"


def test_infer_bank_hint_from_text_detects_supported_bank_keywords():
    text = "Welcome to ICICI Bank credit card statement for your account."
    assert infer_bank_hint_from_text(text) == "ICICI"


def test_infer_bank_hint_prioritizes_statement_header_over_transaction_mentions():
    text = (
        "STATE BANK OF INDIA account statement for April 2025.\n"
        + ("UPI FROM HDFC BANK SOMEONE\n" * 20)
    )
    assert infer_bank_hint_from_text(text) == "SBI"


def test_infer_account_type_hint_from_text_detects_credit_card_and_bank_account():
    cc_text = "Total amount due 12345.00. Payment due date 10/03/2026. Credit limit 500000."
    bank_text = "Savings account statement. Opening balance 1000. Closing balance 5000."
    assert infer_account_type_hint_from_text(cc_text) == "credit_card"
    assert infer_account_type_hint_from_text(bank_text) == "bank_account"
