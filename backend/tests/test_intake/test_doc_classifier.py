from app.engines.intake.doc_classifier import classify_document, classify_uploaded_pdf


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


def test_numeric_statement_without_context_stays_unknown() -> None:
    classified = classify_document("/tmp/0206-statement.pdf")
    assert classified.doc_type == "unknown_pdf"


def test_uploaded_pdf_detects_ppf_statement() -> None:
    classified = classify_uploaded_pdf(
        "PPF-Statement-2025-26.pdf",
        extracted_text="Public Provident Fund account statement interest credited",
    )
    assert classified.doc_type == "ppf_statement"


def test_uploaded_pdf_detects_direct_tax_ack_as_tax_challan() -> None:
    classified = classify_uploaded_pdf(
        "Direct-Tax-Payment-Acknowledgement.pdf",
        extracted_text="Income Tax Challan Receipt CIN NO BSR CODE tax paid",
    )
    assert classified.doc_type == "tax_challan"


def test_filename_challanreceipt_classifies_as_tax_challan() -> None:
    classified = classify_document("/tmp/25082000207786KKBK_ChallanReceipt.pdf")
    assert classified.doc_type == "tax_challan"


def test_ppf_folder_statement_classifies_as_ppf_statement() -> None:
    classified = classify_document("/tmp/BOB/PPF/2926-Statement.pdf")
    assert classified.doc_type == "ppf_statement"


def test_uploaded_pdf_respects_document_type_hint() -> None:
    classified = classify_uploaded_pdf(
        "anything.pdf",
        extracted_text="some text",
        document_type_hint="interest_certificate",
    )
    assert classified.doc_type == "interest_certificate"


def test_uploaded_pdf_respects_demat_alias_document_type_hint() -> None:
    classified = classify_uploaded_pdf(
        "pnl-report.pdf",
        extracted_text="",
        document_type_hint="pnl_statement",
    )
    assert classified.doc_type == "demat_tax_report"


def test_uploaded_pdf_auto_does_not_force_bank_statement_on_ambiguous_text() -> None:
    classified = classify_uploaded_pdf(
        "statement.pdf",
        extracted_text="This is your yearly statement summary and acknowledgement copy.",
        document_type_hint="auto",
    )
    assert classified.doc_type == "unknown_pdf"


def test_uploaded_pdf_cash_word_does_not_trigger_demat_classification() -> None:
    classified = classify_uploaded_pdf(
        "ANKIT-HDFC-CC-STATEMENT.pdf",
        extracted_text=(
            "Credit Card Statement. Cash advance fee. Interest charged on cash advance. "
            "Card number ending 1234. "
            "Minimum amount due and total amount due are shown."
        ),
        document_type_hint="auto",
        bank_hint="HDFC",
    )
    assert classified.doc_type == "credit_card_statement"


def test_uploaded_pdf_fd_list_prefers_fd_report_over_interest_certificate() -> None:
    classified = classify_uploaded_pdf(
        "FD-List.pdf",
        extracted_text=(
            "Fixed Deposit list for FY 2024-25. Interest payable and maturity amount details."
        ),
        document_type_hint="auto",
        bank_hint="ICICI",
    )
    assert classified.doc_type == "fd_report"


def test_uploaded_pdf_challan_prefers_tax_challan_even_with_interest_words() -> None:
    classified = classify_uploaded_pdf(
        "25082000207786KKBK_ChallanReceipt.pdf",
        extracted_text=(
            "Income Tax Challan Receipt. CIN no. BSR code. Tax paid details. "
            "Interest under section 234B."
        ),
        document_type_hint="auto",
    )
    assert classified.doc_type == "tax_challan"
