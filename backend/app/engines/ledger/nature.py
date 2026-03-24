"""Transaction nature inference for metrics and reconciliation."""

from __future__ import annotations

import re

_REFUND_KEYWORDS = (
    "REFUND",
    "REVERSAL",
    "REV",
    "REVERSED",
    "CASHBACK",
    "REWARD",
)

_INTEREST_KEYWORDS = (
    "INTEREST",
    "INT CR",
    "FD INT",
    "SAVINGS INTEREST",
)

_DIVIDEND_KEYWORDS = (
    "DIVIDEND",
)

_SALARY_KEYWORDS = (
    "SALARY",
    "PAYROLL",
    "WAGES",
)

_TAX_KEYWORDS = (
    "TAX",
    "TDS",
    "ADVANCE TAX",
    "CHALLAN",
    "GST",
)

_INVESTMENT_KEYWORDS = (
    "MUTUAL FUND",
    "SIP",
    "NPS",
    "PPF",
    "DEMAT",
    "ZERODHA",
    "GROWW",
    "ICICI DIRECT",
)

_CC_PAYMENT_KEYWORDS = (
    "CREDIT CARD PAYMENT",
    "CARD PAYMENT",
    "CC PAYMENT",
    "CCPMT",
    "CARD PMT",
    "PAYMENT RECEIVED",
    "PAYMENT-THANK YOU",
    "PAYMENT THANK YOU",
    "AUTOPAY",
    "BILLDESK",
    "TELE TRANSFER",
    "TELE TRANSFER CREDIT",
    "TELE TRANSFER CR",
    "CARD PAYMENT RECEIVED",
    "CC BILL PAYMENT",
)

_TRANSFER_CHANNEL_KEYWORDS = (
    "UPI",
    "IMPS",
    "NEFT",
    "RTGS",
    "TRANSFER",
)

_SELF_TRANSFER_KEYWORDS = (
    "SELF",
    "OWN",
    "TO A/C",
    "FROM A/C",
    "ACCOUNT TRANSFER",
)


def infer_transaction_nature(
    description_raw: str,
    direction: str,
    account_type: str | None,
) -> str:
    """Infer transaction nature used in analytics and transfer exclusion."""
    text = _normalize(description_raw)
    dir_norm = (direction or "").lower().strip()
    account_type_norm = (account_type or "").lower().strip()

    if dir_norm == "debit":
        if _contains_any(text, _CC_PAYMENT_KEYWORDS):
            return "transfer_internal"
        if _contains_any(text, _INVESTMENT_KEYWORDS):
            return "investment"
        if _contains_any(text, _TAX_KEYWORDS):
            return "tax"
        if _looks_like_self_transfer(text):
            return "transfer_internal"
        return "expense"

    # credit
    if _contains_any(text, _REFUND_KEYWORDS):
        return "refund"
    if _contains_any(text, _INTEREST_KEYWORDS):
        return "interest_income"
    if _contains_any(text, _DIVIDEND_KEYWORDS):
        return "dividend_income"
    if _contains_any(text, _SALARY_KEYWORDS):
        return "income"
    if account_type_norm == "credit_card":
        if _contains_any(text, _CC_PAYMENT_KEYWORDS) or _looks_like_self_transfer(text):
            return "transfer_internal"
        # Credit entries on card statements are commonly refunds/reversals/adjustments.
        return "refund"
    if _contains_any(text, _CC_PAYMENT_KEYWORDS):
        return "transfer_internal"
    if _looks_like_self_transfer(text):
        return "transfer_internal"
    return "income"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.upper().strip())


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(word in text for word in keywords)


def _looks_like_self_transfer(text: str) -> bool:
    has_channel = _contains_any(text, _TRANSFER_CHANNEL_KEYWORDS)
    has_self = _contains_any(text, _SELF_TRANSFER_KEYWORDS)
    return has_channel and has_self
