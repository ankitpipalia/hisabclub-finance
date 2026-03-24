from datetime import date

from app.engines.parser.templates.axis_cc import AxisCreditCardParser
from app.engines.parser.templates.hdfc_cc import HdfcCreditCardParser


def test_hdfc_detector_ignores_upi_hdfcbank_strings() -> None:
    text = """
AXIS BANK SUPERMONEY RuPay Credit Card
DATE TRANSACTION DETAILS MERCHANT CATEGORY AMOUNT (Rs.) CASHBACK EARNED
01/03/2026 UPI/BLINKIT/BLINKIT.PAYU@HDFCBANK/KIT.PIPALIA@S DEPT STORES 245.00 Dr 7.00 Cr
"""
    assert HdfcCreditCardParser().detect(text) is False
    assert AxisCreditCardParser().detect(text) is True


def test_hdfc_extracts_table_style_summary_fields() -> None:
    text = """
Swiggy HDFC Bank Credit Card
Credit Card Statement
Billing Period 18 Feb, 2026 - 17 Mar, 2026
PREVIOUS STATEMENT DUES FINANCE CHARGES TOTAL AMOUNT DUE
RECEIVED (Current Billing Cycle)
_ C1,776.00
C64,524.23 C66,434.31 + C3,685.71 + C0.00 =
TOTAL CREDIT LIMIT
(Including Cash) AVAILABLE CREDIT LIMIT AVAILABLE CASH LIMIT MINIMUM DUE DUE DATE
C200.00 06 Apr, 2026
C2,10,000 C2,08,224 C84,000
"""
    parser = HdfcCreditCardParser()
    stmt = parser.parse([text], text)

    assert stmt.statement_period_start == date(2026, 2, 18)
    assert stmt.statement_period_end == date(2026, 3, 17)
    assert stmt.total_amount_due == 1776.00
    assert stmt.min_amount_due == 200.00
    assert stmt.due_date == date(2026, 4, 6)
    assert stmt.credit_limit == 210000.00
    assert stmt.available_limit == 208224.00


def test_axis_extracts_summary_and_transaction_amount_with_cashback_column() -> None:
    text = """
AXIS BANK SUPERMONEY RuPay Credit Card
PAYMENT SUMMARY
Total Payment Due Minimum Payment Due Statement Period Payment Due Date Statement Generation Date
22,672.47 Dr 511.00 Dr 17/02/2026 - 15/03/2026 04/04/2026 15/03/2026
Credit Card Number Credit Limit Available Credit Limit Available Cash Limit
652984******3006 212,000.00 189,327.53 21,200.00
Account Summary
DATE TRANSACTION DETAILS MERCHANT CATEGORY AMOUNT (Rs.) CASHBACK EARNED
17/02/2026 UPI/NAVAB HANIFBHAI KURESHI/Q914101747@YBL/.PIP CLOTH STORES 1,200.00 Dr 12.00 Cr
20/02/2026 BBPS PAYMENT RECEIVED - MK016051BAAM81MEE000 5,347.70 Cr 0.00 Dr
"""
    parser = AxisCreditCardParser()
    stmt = parser.parse([text], text)

    assert stmt.statement_period_start == date(2026, 2, 17)
    assert stmt.statement_period_end == date(2026, 3, 15)
    assert stmt.due_date == date(2026, 4, 4)
    assert stmt.total_amount_due == 22672.47
    assert stmt.min_amount_due == 511.00
    assert stmt.credit_limit == 212000.00
    assert stmt.available_limit == 189327.53
    assert len(stmt.transactions) == 2
    assert stmt.transactions[0].amount == 1200.00
    assert stmt.transactions[0].direction == "debit"
    assert stmt.transactions[1].amount == 5347.70
    assert stmt.transactions[1].direction == "credit"
