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
        return _classify_pdf_text(text=text, bank_hint=bank_hint)

    if ext in {"xlsx", "xls", "csv"}:
        if _has_any(text, ("capital gains", "stcgt", "ltcgt", "tax report")):
            return ClassifiedDocument("demat_tax_report")
        if _has_any(text, ("order history", "trade", "f&o", "fno", "p&l", "pnl")):
            return ClassifiedDocument("demat_trade_report")
        if _has_any(text, ("holdings", "mutual funds", "stocks")):
            return ClassifiedDocument("demat_holdings")
        return ClassifiedDocument("spreadsheet")

    return ClassifiedDocument("unsupported")


def classify_uploaded_pdf(
    filename: str,
    extracted_text: str | None = None,
    *,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    document_type_hint: str | None = None,
) -> ClassifiedDocument:
    """Classify a manually uploaded PDF using filename + extracted content.

    The upload endpoint can pass explicit hints. If provided, hints are treated
    as strong routing signals before keyword classification.
    """
    normalized_doc_hint = _normalize_doc_type_hint(document_type_hint)
    normalized_account_hint = (account_type_hint or "").strip().lower()
    merged_text = f"{filename} {extracted_text or ''}".lower()
    merged_text = merged_text.replace("_", " ").replace("-", " ")
    inferred_bank = bank_hint or _infer_bank_hint(merged_text)

    if normalized_doc_hint and normalized_doc_hint != "auto":
        return ClassifiedDocument(
            doc_type=normalized_doc_hint,
            bank_hint=inferred_bank,
        )
    if normalized_account_hint == "credit_card":
        return ClassifiedDocument("credit_card_statement", bank_hint=inferred_bank)
    if normalized_account_hint in {"bank_account", "savings", "current"}:
        return ClassifiedDocument("bank_statement", bank_hint=inferred_bank)

    classified = _classify_pdf_text(text=merged_text, bank_hint=inferred_bank)
    if classified.doc_type == "unknown_pdf":
        # Backward-safe fallback: legacy upload flow expected statement parsing.
        return ClassifiedDocument("bank_statement", bank_hint=inferred_bank)
    return classified


def _infer_bank_hint(text: str) -> str | None:
    banks = {
        "hdfc": "HDFC",
        "hdfc bank": "HDFC",
        "axis": "AXIS",
        "axis bank": "AXIS",
        "sbi": "SBI",
        "state bank of india": "SBI",
        "icici": "ICICI",
        "icici bank": "ICICI",
        "kotak": "KOTAK",
        "kotak mahindra bank": "KOTAK",
        "pnb": "PNB",
        "punjab national bank": "PNB",
        "bob": "BOB",
        "bank of baroda": "BOB",
        "canara": "CANARA",
        "canara bank": "CANARA",
        "union bank of india": "UNION",
        "union bank": "UNION",
        "indian bank": "INDIAN",
        "bank of india": "BOI",
        "boi": "BOI",
        "idbi bank": "IDBI",
        "idbi": "IDBI",
        "indusind bank": "INDUSIND",
        "indusind": "INDUSIND",
        "yes bank": "YES",
        "yes": "YES",
        "federal bank": "FEDERAL",
        "federal": "FEDERAL",
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


def _classify_pdf_text(*, text: str, bank_hint: str | None) -> ClassifiedDocument:
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

    if _has_any(text, ("ppf statement", "public provident fund", "ppf account", " ppf ")):
        return ClassifiedDocument("ppf_statement", bank_hint=bank_hint)
    if _has_any(text, ("interest", "tds certificate", "interest certificate")):
        return ClassifiedDocument("interest_certificate", bank_hint=bank_hint)
    if _has_any(text, ("form16", "form-16", "partb")):
        return ClassifiedDocument("tax_form", "form16")
    if _has_any(text, ("form12bb", "12bb")):
        return ClassifiedDocument("tax_form", "form12bb")
    if _has_any(
        text,
        (
            "direct tax payment acknowledgement",
            "income tax challan",
            "challan receipt",
            "challanreceipt",
            "challan no",
            "cin no",
            "bsr code",
            "tax paid",
            "e-pay tax",
            "tax payment receipt",
        ),
    ):
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


_DOC_TYPE_HINT_ALIASES: dict[str, str] = {
    "auto": "auto",
    "bank_statement": "bank_statement",
    "bank_account_statement": "bank_statement",
    "saving_statement": "bank_statement",
    "savings_statement": "bank_statement",
    "credit_card_statement": "credit_card_statement",
    "interest_certificate": "interest_certificate",
    "fd_report": "fd_report",
    "fixed_deposit": "fd_report",
    "tax_challan": "tax_challan",
    "direct_tax_ack": "tax_challan",
    "direct_tax_payment_acknowledgement": "tax_challan",
    "ppf_statement": "ppf_statement",
    "tax_form": "tax_form",
    "dividend_report": "dividend_report",
    "demat_tax_report": "demat_tax_report",
    "demat_trade_report": "demat_trade_report",
    "demat_holdings": "demat_holdings",
    "stock_holdings": "demat_holdings",
    "mutual_fund_holdings": "demat_holdings",
    "balance_statement": "demat_holdings",
    "capital_gains_statement": "demat_tax_report",
    "pnl_statement": "demat_tax_report",
    "p_and_l_statement": "demat_tax_report",
    "contract_note_report": "demat_trade_report",
}


def _normalize_doc_type_hint(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _DOC_TYPE_HINT_ALIASES.get(key)
