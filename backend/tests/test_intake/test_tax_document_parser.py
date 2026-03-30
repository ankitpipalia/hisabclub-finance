from app.engines.intake.tax_document_parser import extract_tax_document_metadata


def test_extract_interest_certificate_metadata() -> None:
    text = """
Interest Certificate FY 2024-25
Total Interest Paid: 12,345.67
Total TDS Deducted: 1,234.00
"""
    metadata = extract_tax_document_metadata(
        doc_type="interest_certificate",
        text=text,
        source_filename="interest.pdf",
    )
    assert metadata["financial_year"] == "2024-25"
    assert metadata["interest_amount"] == 12345.67
    assert metadata["tds_amount"] == 1234.0


def test_extract_tax_challan_metadata() -> None:
    text = """
Income Tax Challan Receipt
CIN No: 1234ABCD5678
BSR Code: 1234567
Challan No: 00987
Date of Deposit: 30/03/2026
Total Amount Paid: 55,000.00
"""
    metadata = extract_tax_document_metadata(
        doc_type="tax_challan",
        text=text,
        source_filename="challan.pdf",
    )
    assert metadata["tax_paid_amount"] == 55000.0
    assert metadata["challan_date"] == "2026-03-30"
    assert metadata["bsr_code"] == "1234567"
    assert metadata["challan_serial_no"] == "00987"


def test_extract_ppf_statement_metadata() -> None:
    text = """
PPF Account Statement
PPF A/C No: 123456789012
Opening Balance: 1,00,000.00
Subscription Amount: 50,000.00
Interest Credited: 7,500.00
Closing Balance: 1,57,500.00
"""
    metadata = extract_tax_document_metadata(
        doc_type="ppf_statement",
        text=text,
        source_filename="ppf.pdf",
    )
    assert metadata["ppf_account_masked"] == "XXXXXXXX9012"
    assert metadata["opening_balance"] == 100000.0
    assert metadata["contribution_amount"] == 50000.0
    assert metadata["interest_amount"] == 7500.0
    assert metadata["closing_balance"] == 157500.0
