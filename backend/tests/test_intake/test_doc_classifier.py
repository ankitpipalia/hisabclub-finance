import io
import zipfile
from xml.sax.saxutils import escape

from app.engines.intake.doc_classifier import (
    classify_document,
    classify_uploaded_pdf,
    classify_uploaded_spreadsheet,
    infer_uploaded_bank_hint,
)


def _make_minimal_xlsx(shared_strings: list[str]) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
    shared = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    for value in shared_strings:
        shared.append(f"<si><t>{escape(value)}</t></si>")
    shared.append("</sst>")
    shared_strings_xml = "".join(shared)
    rows = []
    for idx, _value in enumerate(shared_strings, start=1):
        rows.append(
            f'<row r="{idx}"><c r="A{idx}" t="s"><v>{idx - 1}</v></c></row>'
        )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        + "".join(rows)
        + '</sheetData></worksheet>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/sharedStrings.xml", shared_strings_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


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


def test_uploaded_spreadsheet_uses_content_for_trade_report_detection() -> None:
    data = _make_minimal_xlsx(
        [
            "Client ID",
            "HQQ499",
            "Annual Global Transaction Statement for Equity from 2024-04-01 to 2025-03-31",
            "Charges",
            "Buy Quantity",
            "Sell Quantity",
            "F&O",
        ]
    )
    classified = classify_uploaded_spreadsheet("Demat/Zerodha/agts-HQQ499.xlsx", data)
    assert classified.doc_type == "demat_trade_report"


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


def test_uploaded_pdf_detects_ppf_ledger_before_generic_bank_score() -> None:
    classified = classify_uploaded_pdf(
        "BOB/PPF/2926-Statement.pdf",
        extracted_text=(
            "PPF ACCOUNT LEDGER\n"
            "PPF Account No: 036XXXXXXXXXXXXXX926\n"
            "Statement Date: 31 Mar 2025\n"
            "Date Withdrawal Deposit Balance\n"
        ),
        document_type_hint="auto",
        bank_hint="BOB",
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


def test_uploaded_pdf_uses_folder_path_for_ppf_classification() -> None:
    classified = classify_uploaded_pdf(
        "BOB/PPF/2926-Statement.pdf",
        extracted_text="Yearly account statement summary.",
        document_type_hint="auto",
    )
    assert classified.doc_type == "ppf_statement"


def test_uploaded_pdf_respects_document_type_hint() -> None:
    classified = classify_uploaded_pdf(
        "anything.pdf",
        extracted_text="some text",
        document_type_hint="interest_certificate",
    )
    assert classified.doc_type == "interest_certificate"


def test_infer_uploaded_bank_hint_prefers_path_over_security_names() -> None:
    bank_hint = infer_uploaded_bank_hint(
        "Demat/ICICI STOCK & MUTUAL FUND DETAILS 2024-2025/Ankit Pipalia ICICI Direct Stock Demat Holdings As on 31.03.2025.pdf",
        extracted_text="BANK OF BARODA 228.53 BUY SELL GTT Sell",
    )
    assert bank_hint == "ICICI"


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


def test_uploaded_pdf_interest_certificate_beats_generic_bank_statement_score() -> None:
    classified = classify_uploaded_pdf(
        "ICICI/Interest-TDS-Certificate.pdf",
        extracted_text=(
            "Interest Certificate\n"
            "Please find below confirmation of the Interest paid and Tax withheld.\n"
            "Account Number XXXXX9719 Statement Date 31 March 2025\n"
        ),
        document_type_hint="auto",
        bank_hint="ICICI",
    )
    assert classified.doc_type == "interest_certificate"


def test_uploaded_pdf_interest_tds_does_not_match_fd_substring() -> None:
    classified = classify_uploaded_pdf(
        "ICICI/Interest-TDS-Certificate.pdf",
        extracted_text=(
            "Interest Certificate\n"
            "Tax withheld and interest paid summary for the year.\n"
        ),
        document_type_hint="auto",
        bank_hint="ICICI",
    )
    assert classified.doc_type == "interest_certificate"


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


def test_uploaded_investment_portfolio_is_not_bank_statement() -> None:
    classified = classify_uploaded_pdf(
        "Demat/ICICI STOCK & MUTUAL FUND DETAILS 2024-2025/PIPALIA ANKIT.pdf",
        extracted_text=(
            "Consolidated Investment Portfolio\n"
            "Your Investment Portfolio makes it easy for you to monitor your financial position.\n"
            "Customer: PIPALIA ANKIT\n"
            "Account Number: 8505610624 Statement Date: 31 March 2025\n"
            "The Consolidated Investment Portfolio provides a consolidated view of your investments.\n"
        ),
        document_type_hint="auto",
        bank_hint="ICICI",
    )
    assert classified.doc_type == "demat_holdings"


def test_uploaded_demat_holdings_beats_trade_keywords() -> None:
    classified = classify_uploaded_pdf(
        "Demat/ICICI STOCK & MUTUAL FUND DETAILS 2024-2025/Ankit Pipalia ICICI Direct Stock Demat Holdings As on 31.03.2025.pdf",
        extracted_text=(
            "ICICI Direct https://secure.icicidirect.com/trading/equity/DematAllocation\n"
            "Demat Holdings As on 31.03.2025\n"
            "Buy Sell GTT Sell\n"
            "The Total Demat Balance reflects free balance held in your demat account.\n"
        ),
        document_type_hint="auto",
    )
    assert classified.doc_type == "demat_holdings"


def test_uploaded_mutual_fund_valuation_report_is_holdings_not_dividend() -> None:
    classified = classify_uploaded_pdf(
        "Demat/ICICI STOCK & MUTUAL FUND DETAILS 2024-2025/Ankit Pipalia Mutual Fund Holdings As on 31.03.2025.pdf",
        extracted_text=(
            "Client Wise Valuation Report\n"
            "Mutual Fund Summary\n"
            "Invested Amount Reinvested Dividend Paid Dividend Current Amount\n"
            "Current Amount 276193.08\n"
        ),
        document_type_hint="auto",
    )
    assert classified.doc_type == "demat_holdings"


def test_uploaded_form16_part_a_is_tax_form_not_interest_certificate() -> None:
    classified = classify_uploaded_pdf(
        "Form-16/april-november (SIMFORM)/FSYPXXXXXD_2024-2025.pdf",
        extracted_text=(
            "FORM NO. 16\n"
            "PART A\n"
            "Certificate under Section 203 of the Income-tax Act, 1961 for tax deducted at source on salary paid to an employee under section 192.\n"
        ),
        document_type_hint="auto",
    )
    assert classified.doc_type == "tax_form"


def test_uploaded_bank_statement_with_groww_transaction_stays_bank_statement() -> None:
    classified = classify_uploaded_pdf(
        "SBI/statement-40571652298.pdf",
        extracted_text=(
            "Account Number 00000040571652298\n"
            "Account Description REGULAR SB CHQ-INDIVIDUALS\n"
            "Branch RANI TOWER - RAJKOT\n"
            "IFS Code SBIN0060471\n"
            "Balance as on 1 Apr 2024 54,575.10\n"
            "Account Statement from 1 Apr 2024 to 31 Mar 2025\n"
            "Txn Date Value Description Ref No./Cheque Debit Credit Balance\n"
            "2 Apr 2024 TO TRANSFER UPI/DR/445932393524/Nextbill/HDFC/groww.razo/Payvi-\n"
        ),
        document_type_hint="auto",
    )
    assert classified.doc_type == "bank_statement"
    assert classified.bank_hint == "SBI"


def test_uploaded_bank_statement_with_dividend_text_stays_bank_statement() -> None:
    classified = classify_uploaded_pdf(
        "ICICI/9719-statement.pdf",
        extracted_text=(
            "Account Statement\n"
            "Savings Account Number XXXXX9719\n"
            "IFSC ICIC0001234\n"
            "Opening Balance 12,500.00\n"
            "Closing Balance 19,450.20\n"
            "Transaction Details Debit Credit Balance\n"
            "BY TRANSFER UPI/CR/123456/DIVIDEND FROM ABC LTD 250.00\n"
        ),
        bank_hint="ICICI",
        document_type_hint="auto",
    )
    assert classified.doc_type == "bank_statement"
    assert classified.bank_hint == "ICICI"
