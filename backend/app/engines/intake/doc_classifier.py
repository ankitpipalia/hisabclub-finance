"""Document classification for manual uploads and folder intake."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.engines.parser.hints import infer_bank_hint_from_text, normalize_bank_hint


@dataclass
class ClassifiedDocument:
    doc_type: str
    doc_subtype: str | None = None
    bank_hint: str | None = None
    account_type_hint: str | None = None
    confidence: float = 0.0
    source: str = "rules"
    reason: str | None = None


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
            return ClassifiedDocument("demat_tax_report", confidence=0.9)
        if _has_any(text, ("order history", "trade", "f&o", "fno", "p&l", "pnl")):
            return ClassifiedDocument("demat_trade_report", confidence=0.9)
        if _has_any(text, ("holdings", "mutual funds", "stocks")):
            return ClassifiedDocument("demat_holdings", confidence=0.85)
        return ClassifiedDocument("spreadsheet", confidence=0.6)

    return ClassifiedDocument("unsupported", confidence=1.0)


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
    normalized_doc_hint = normalize_doc_type_hint(document_type_hint)
    normalized_account_hint = (account_type_hint or "").strip().lower()
    merged_text = f"{filename} {extracted_text or ''}".lower()
    merged_text = merged_text.replace("_", " ").replace("-", " ")
    inferred_bank = normalize_bank_hint(bank_hint) or _infer_bank_hint(merged_text)

    if normalized_doc_hint and normalized_doc_hint != "auto":
        return ClassifiedDocument(
            doc_type=normalized_doc_hint,
            bank_hint=inferred_bank,
            account_type_hint=_account_hint_for_doc_type(normalized_doc_hint),
            confidence=1.0,
            source="user_hint",
            reason="document_type_hint",
        )
    if normalized_account_hint == "credit_card":
        return ClassifiedDocument(
            "credit_card_statement",
            bank_hint=inferred_bank,
            account_type_hint="credit_card",
            confidence=0.96,
            source="user_hint",
            reason="account_type_hint=credit_card",
        )
    if normalized_account_hint in {"bank_account", "savings", "current"}:
        return ClassifiedDocument(
            "bank_statement",
            bank_hint=inferred_bank,
            account_type_hint="bank_account",
            confidence=0.96,
            source="user_hint",
            reason="account_type_hint=bank_account",
        )

    classified = _classify_pdf_text(text=merged_text, bank_hint=inferred_bank)
    return classified


def _infer_bank_hint(text: str) -> str | None:
    return infer_bank_hint_from_text(text)


def _has_any(text: str, keys: tuple[str, ...]) -> bool:
    return any(k in text for k in keys)


def _is_investment_document(text: str) -> bool:
    if _has_any(
        text,
        (
            "mutual fund",
            "cams",
            "kfin",
            "groww",
            "zerodha",
            "demat",
            "portfolio",
            "holdings",
            "consolidated account statement",
            "capital gains",
            "dividend",
            "statement of holdings",
        ),
    ):
        return True

    # Keep short investment abbreviations strict to avoid false positives
    # such as "cash", "business", etc.
    return any(
        _has_word(text, token)
        for token in ("cas", "coin", "nse", "bse")
    )


def _classify_pdf_text(*, text: str, bank_hint: str | None) -> ClassifiedDocument:
    # Detect non-bank financial documents before generic "statement" matching
    # to avoid false positives on mutual-fund and demat statements.
    if _is_investment_document(text):
        if _has_any(text, ("capital gains", "stcgt", "ltcgt", "gain/loss", "tax report")):
            return ClassifiedDocument("demat_tax_report", confidence=0.93)
        if _has_any(text, ("trade", "contract note", "order history", "f&o", "fno", "p&l", "pnl")):
            return ClassifiedDocument("demat_trade_report", confidence=0.93)
        if _has_any(text, ("dividend",)):
            return ClassifiedDocument("dividend_report", confidence=0.88)
        return ClassifiedDocument("demat_holdings", confidence=0.86)

    if _has_any(text, ("ppf statement", "public provident fund", "ppf account", " ppf ")):
        return ClassifiedDocument("ppf_statement", bank_hint=bank_hint, confidence=0.95)
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
        return ClassifiedDocument("tax_challan", confidence=0.95)
    if _has_any(text, ("form16", "form-16", "partb")):
        return ClassifiedDocument("tax_form", "form16", confidence=0.9)
    if _has_any(text, ("form12bb", "12bb")):
        return ClassifiedDocument("tax_form", "form12bb", confidence=0.9)
    if _has_any(text, ("fd", "fixed deposit")):
        return ClassifiedDocument("fd_report", bank_hint=bank_hint, confidence=0.84)
    if _looks_like_interest_certificate(text):
        return ClassifiedDocument("interest_certificate", bank_hint=bank_hint, confidence=0.88)
    if _has_any(text, ("capital gains", "stcgt", "ltcgt", "p&l", "pnl")):
        return ClassifiedDocument("demat_tax_report", confidence=0.86)
    if _has_any(text, ("holdings", "balance statement")):
        return ClassifiedDocument("demat_holdings", confidence=0.82)
    if _has_any(text, ("dividend",)):
        return ClassifiedDocument("dividend_report", confidence=0.84)
    if bank_hint and _has_any(
        text,
        ("credit card statement", "card statement", "cc statement", "cc stmt"),
    ):
        return ClassifiedDocument(
            "credit_card_statement",
            bank_hint=bank_hint,
            account_type_hint="credit_card",
            confidence=0.76,
            reason="bank_hint+card_statement_phrase",
        )
    if bank_hint and _has_any(
        text,
        ("account statement", "savings account", "current account", "passbook"),
    ):
        return ClassifiedDocument(
            "bank_statement",
            bank_hint=bank_hint,
            account_type_hint="bank_account",
            confidence=0.74,
            reason="bank_hint+account_statement_phrase",
        )

    credit_score = _keyword_score(
        text,
        (
            "credit card statement",
            "credit card no",
            "card number",
            "minimum amount due",
            "total amount due",
            "payment due date",
            "credit limit",
            "available limit",
            "card statement",
            "cc statement",
            "cc stmt",
            "card account",
            "cash limit",
            "cash advance",
            "card ending",
        ),
    )
    bank_score = _keyword_score(
        text,
        (
            "savings account",
            "current account",
            "account statement",
            "passbook",
            "opening balance",
            "closing balance",
            "available balance",
            "ifsc",
            "branch",
            "account number",
            "a/c no",
            "a/c number",
            "upi/",
            "neft",
            "rtgs",
            "imps",
            "debit",
            "credit",
            "withdrawal",
            "deposit",
        ),
    )
    # Generic statement words alone should not force classification.
    if _has_any(text, ("statement", "mini statement", "transaction statement", "e statement")):
        bank_score += 1

    if credit_score >= 8 and credit_score >= bank_score + 2:
        confidence = _confidence_from_score(credit_score)
        return ClassifiedDocument(
            "credit_card_statement",
            bank_hint=bank_hint,
            account_type_hint="credit_card",
            confidence=confidence,
            reason=f"credit_score={credit_score},bank_score={bank_score}",
        )
    if bank_score >= 8 and bank_score >= credit_score + 2:
        confidence = _confidence_from_score(bank_score)
        return ClassifiedDocument(
            "bank_statement",
            bank_hint=bank_hint,
            account_type_hint="bank_account",
            confidence=confidence,
            reason=f"bank_score={bank_score},credit_score={credit_score}",
        )
    if bank_hint and max(bank_score, credit_score) >= 6:
        if credit_score > bank_score:
            return ClassifiedDocument(
                "credit_card_statement",
                bank_hint=bank_hint,
                account_type_hint="credit_card",
                confidence=_confidence_from_score(credit_score, base=0.62),
                reason=f"bank_hint+credit_score={credit_score}",
            )
        return ClassifiedDocument(
            "bank_statement",
            bank_hint=bank_hint,
            account_type_hint="bank_account",
            confidence=_confidence_from_score(bank_score, base=0.62),
            reason=f"bank_hint+bank_score={bank_score}",
        )
    return ClassifiedDocument(
        "unknown_pdf",
        bank_hint=bank_hint,
        confidence=0.2,
        reason=f"low_confidence bank_score={bank_score},credit_score={credit_score}",
    )


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


def normalize_doc_type_hint(value: str | None) -> str | None:
    """Public wrapper used by LLM/doc-routing layers."""
    return _normalize_doc_type_hint(value)


def _keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    score = 0
    for keyword in keywords:
        if keyword in text:
            token_count = len(keyword.split())
            score += 3 if token_count >= 3 else 2
    return score


def _has_word(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def _looks_like_interest_certificate(text: str) -> bool:
    if _has_any(text, ("tds certificate", "interest certificate")):
        return True
    if "certificate" not in text:
        return False
    return _has_any(
        text,
        (
            "total interest",
            "interest credited",
            "interest paid",
            "interest amount",
            "interest accrued",
            "tds deducted",
            "tds amount",
        ),
    )


def _confidence_from_score(score: int, *, base: float = 0.58) -> float:
    conf = base + (min(score, 18) / 40.0)
    return max(0.0, min(conf, 0.97))


def _account_hint_for_doc_type(doc_type: str | None) -> str | None:
    if doc_type == "credit_card_statement":
        return "credit_card"
    if doc_type == "bank_statement":
        return "bank_account"
    return None
