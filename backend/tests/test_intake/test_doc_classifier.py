from app.engines.intake.doc_classifier import classify_document


def test_mutual_fund_statement_is_not_bank_statement() -> None:
    classified = classify_document(
        "/tmp/Mutual_Funds_ELSS_Statement_01-04-2024_31-03-2025.pdf"
    )
    assert classified.doc_type == "demat_holdings"
    assert classified.bank_hint is None


def test_groww_balance_statement_classifies_as_demat_holdings() -> None:
    classified = classify_document(
        "/tmp/Groww_Balance_Statement_9107616824_01-04-2024_31-03-2025.pdf"
    )
    assert classified.doc_type == "demat_holdings"


def test_kotak_credit_card_statement_keeps_bank_hint() -> None:
    classified = classify_document("/tmp/ANKIT-KOTAK-CC-STATEMENT.pdf")
    assert classified.doc_type == "credit_card_statement"
    assert classified.bank_hint == "KOTAK"


def test_numeric_statement_defaults_to_bank_statement() -> None:
    classified = classify_document("/tmp/0206-statement.pdf")
    assert classified.doc_type == "bank_statement"
