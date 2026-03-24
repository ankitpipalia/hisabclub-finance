"""Filename/path based document classification for local bulk intake."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClassifiedDocument:
    doc_type: str
    doc_subtype: str | None = None
    bank_hint: str | None = None


def classify_document(path: str) -> ClassifiedDocument:
    p = Path(path)
    ext = p.suffix.lower().lstrip(".")
    text = f"{p.name} {' '.join(part for part in p.parts)}".lower()
    text = text.replace("_", " ").replace("-", " ")

    bank_hint = _infer_bank_hint(text)

    if ext == "pdf":
        # Detect non-bank financial documents before generic "statement" matching
        # to avoid false positives on mutual-fund and demat statements.
        if _is_investment_document(text):
            if _has_any(text, ("capital gains", "stcgt", "ltcgt", "gain/loss", "tax report")):
                return ClassifiedDocument("demat_tax_report")
            if _has_any(text, ("trade", "contract note", "order history", "f&o", "fno", "p&l", "pnl")):
                return ClassifiedDocument("demat_trade_report")
            if _has_any(text, ("dividend",)):
                return ClassifiedDocument("dividend_report")
            return ClassifiedDocument("demat_holdings")

        if _has_any(text, ("interest", "tds certificate", "interest certificate")):
            return ClassifiedDocument("interest_certificate", bank_hint=bank_hint)
        if _has_any(text, ("form16", "form-16", "partb")):
            return ClassifiedDocument("tax_form", "form16")
        if _has_any(text, ("form12bb", "12bb")):
            return ClassifiedDocument("tax_form", "form12bb")
        if _has_any(text, ("challan", "receipt")):
            return ClassifiedDocument("tax_challan")
        if _has_any(text, ("capital gains", "stcgt", "ltcgt", "p&l", "pnl")):
            return ClassifiedDocument("demat_tax_report")
        if _has_any(text, ("holdings", "balance statement")):
            return ClassifiedDocument("demat_holdings")
        if _has_any(text, ("dividend",)):
            return ClassifiedDocument("dividend_report")
        if _has_any(text, ("fd", "fixed deposit")):
            return ClassifiedDocument("fd_report", bank_hint=bank_hint)
        if _has_any(
            text,
            (
                "statement",
                "account statement",
                "mini statement",
                "stmt",
                "passbook",
                "transaction statement",
                "e statement",
            ),
        ):
            if _has_any(text, ("cc", "credit card", "card statement")):
                return ClassifiedDocument("credit_card_statement", bank_hint=bank_hint)
            return ClassifiedDocument("bank_statement", bank_hint=bank_hint)
        if bank_hint and _has_any(
            text,
            ("credit card", "card", "cc", "account", "passbook", "txn", "transaction"),
        ):
            if _has_any(text, ("credit card", "card", "cc")):
                return ClassifiedDocument("credit_card_statement", bank_hint=bank_hint)
            return ClassifiedDocument("bank_statement", bank_hint=bank_hint)
        return ClassifiedDocument("unknown_pdf", bank_hint=bank_hint)

    if ext in {"xlsx", "xls", "csv"}:
        if _has_any(text, ("capital gains", "stcgt", "ltcgt", "tax report")):
            return ClassifiedDocument("demat_tax_report")
        if _has_any(text, ("order history", "trade", "f&o", "fno", "p&l", "pnl")):
            return ClassifiedDocument("demat_trade_report")
        if _has_any(text, ("holdings", "mutual funds", "stocks")):
            return ClassifiedDocument("demat_holdings")
        return ClassifiedDocument("spreadsheet")

    return ClassifiedDocument("unsupported")


def _infer_bank_hint(text: str) -> str | None:
    banks = {
        "hdfc": "HDFC",
        "axis": "AXIS",
        "sbi": "SBI",
        "icici": "ICICI",
        "kotak": "KOTAK",
        "bob": "BOB",
        "bank of baroda": "BOB",
    }
    for key, value in banks.items():
        if key in text:
            return value
    return None


def _has_any(text: str, keys: tuple[str, ...]) -> bool:
    return any(k in text for k in keys)


def _is_investment_document(text: str) -> bool:
    return _has_any(
        text,
        (
            "mutual fund",
            "cams",
            "kfin",
            "groww",
            "zerodha",
            "coin",
            "demat",
            "portfolio",
            "holdings",
            "consolidated account statement",
            "cas",
            "capital gains",
            "dividend",
            "nse",
            "bse",
            "statement of holdings",
        ),
    )
