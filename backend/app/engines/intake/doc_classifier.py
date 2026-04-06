"""Document classification for manual uploads and folder intake."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

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
    text = text.replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")

    bank_hint = _infer_bank_hint(text)

    if ext == "pdf":
        return _classify_pdf_text(text=text, bank_hint=bank_hint)

    if ext in {"xlsx", "xls", "csv"}:
        return _classify_spreadsheet_text(text=text, bank_hint=bank_hint)

    return ClassifiedDocument("unsupported", confidence=1.0)


def classify_uploaded_spreadsheet(
    filename: str,
    content: bytes,
    *,
    bank_hint: str | None = None,
    document_type_hint: str | None = None,
) -> ClassifiedDocument:
    normalized_doc_hint = normalize_doc_type_hint(document_type_hint)
    inferred_bank = normalize_bank_hint(bank_hint) or _infer_bank_hint(filename)
    if normalized_doc_hint and normalized_doc_hint != "auto":
        return ClassifiedDocument(
            doc_type=normalized_doc_hint,
            bank_hint=inferred_bank,
            account_type_hint=_account_hint_for_doc_type(normalized_doc_hint),
            confidence=1.0,
            source="user_hint",
            reason="document_type_hint",
        )

    extracted_text = _extract_spreadsheet_text(filename, content)
    merged = f"{filename} {extracted_text}".lower()
    merged = merged.replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")
    return _classify_spreadsheet_text(text=merged, bank_hint=inferred_bank)


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
    merged_text = (
        merged_text.replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")
    )
    bank_routing_text = f"{filename} {_bank_routing_excerpt(extracted_text or '')}".lower()
    bank_routing_text = bank_routing_text.replace("_", " ").replace("-", " ")
    inferred_bank = normalize_bank_hint(bank_hint) or _infer_bank_hint(bank_routing_text)

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


def infer_uploaded_bank_hint(filename: str, extracted_text: str | None = None) -> str | None:
    filename_text = filename.lower().replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")
    filename_hint = _infer_bank_hint(filename_text)
    if filename_hint:
        return filename_hint
    routing_text = f"{filename} {_bank_routing_excerpt(extracted_text or '')}".lower()
    routing_text = (
        routing_text.replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")
    )
    return _infer_bank_hint(routing_text)


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


def _classify_spreadsheet_text(*, text: str, bank_hint: str | None) -> ClassifiedDocument:
    if _has_any(
        text,
        (
            "global transaction statement",
            "charges account head amount",
            "buy quantity",
            "sell quantity",
            "buy value",
            "sell value",
            "tradebook",
            "trade book",
            "order history",
            "f&o",
            "fno",
            "equity from",
            "mutual funds from",
            "commodity from",
            "currency from",
            "segment",
        ),
    ):
        return ClassifiedDocument("demat_trade_report", bank_hint=bank_hint, confidence=0.94)
    if _has_any(text, ("capital gains", "stcgt", "ltcgt", "tax report", "gain/loss")):
        return ClassifiedDocument("demat_tax_report", bank_hint=bank_hint, confidence=0.9)
    if _has_any(
        text,
        (
            "holdings",
            "holding",
            "valuation report",
            "mutual fund summary",
            "current amount",
            "invested amount",
            "portfolio",
            "stocks",
            "mutual funds",
        ),
    ):
        return ClassifiedDocument("demat_holdings", bank_hint=bank_hint, confidence=0.88)
    return ClassifiedDocument("spreadsheet", bank_hint=bank_hint, confidence=0.6)


def _extract_spreadsheet_text(filename: str, content: bytes, *, max_chars: int = 30000) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return content.decode("utf-8", errors="ignore")[:max_chars]
    if suffix == ".xlsx":
        try:
            return _extract_xlsx_text(content, max_chars=max_chars)
        except Exception:
            return ""
    if suffix == ".xls":
        return content.decode("latin-1", errors="ignore")[:max_chars]
    return ""


def _extract_xlsx_text(content: bytes, *, max_chars: int = 30000) -> str:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    fragments: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall("x:si", ns):
                value = "".join(node.text or "" for node in si.findall(".//x:t", ns))
                if value:
                    shared_strings.append(value)
                    fragments.append(value)
                    if sum(len(part) for part in fragments) >= max_chars:
                        break

        workbook_name = "xl/workbook.xml"
        if workbook_name in archive.namelist():
            workbook = ET.fromstring(archive.read(workbook_name))
            for sheet in workbook.findall(".//x:sheets/x:sheet", ns):
                name = sheet.attrib.get("name")
                if name:
                    fragments.append(name)

        for name in archive.namelist():
            if "xl/worksheets/" not in name or not name.endswith(".xml"):
                continue
            root = ET.fromstring(archive.read(name))
            for cell in root.findall(".//x:c", ns):
                cell_type = cell.attrib.get("t")
                value_node = cell.find("x:v", ns)
                if value_node is None or value_node.text is None:
                    continue
                value = value_node.text
                if cell_type == "s":
                    try:
                        idx = int(value)
                    except ValueError:
                        continue
                    if 0 <= idx < len(shared_strings):
                        fragments.append(shared_strings[idx])
                else:
                    fragments.append(value)
                if sum(len(part) for part in fragments) >= max_chars:
                    break
            if sum(len(part) for part in fragments) >= max_chars:
                break

    text = " ".join(part.strip() for part in fragments if part and part.strip())
    return text[:max_chars]


def _classify_pdf_text(*, text: str, bank_hint: str | None) -> ClassifiedDocument:
    header_text = _header_excerpt(text)

    # Specific header-level document cues should outrank generic statement
    # vocabulary like "account number" or "statement date".
    if _has_any(header_text, ("ppf statement", "public provident fund", "ppf account", " ppf ")):
        return ClassifiedDocument("ppf_statement", bank_hint=bank_hint, confidence=0.95)
    if _has_any(
        header_text,
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
    if _has_any(header_text, ("form16", "form-16", "form no. 16", "parta", "part a", "partb", "part b")):
        return ClassifiedDocument("tax_form", "form16", confidence=0.9)
    if _has_any(header_text, ("form12bb", "12bb")):
        return ClassifiedDocument("tax_form", "form12bb", confidence=0.9)
    if "fixed deposit" in header_text or _has_word(header_text, "fd"):
        return ClassifiedDocument("fd_report", bank_hint=bank_hint, confidence=0.84)
    if _looks_like_interest_certificate(header_text):
        return ClassifiedDocument("interest_certificate", bank_hint=bank_hint, confidence=0.88)
    if _is_investment_document(header_text):
        if _has_any(
            header_text,
            (
                "investment portfolio",
                "consolidated investment portfolio",
                "valuation report",
                "mutual fund summary",
                "demat holdings",
                "statement of holdings",
                "current amount",
                "holdings as on",
                "asset composition",
            ),
        ):
            return ClassifiedDocument("demat_holdings", confidence=0.9)
        if _has_any(header_text, ("capital gains", "stcgt", "ltcgt", "gain/loss", "tax report")):
            return ClassifiedDocument("demat_tax_report", confidence=0.93)
        if _has_any(header_text, ("trade", "contract note", "order history", "f&o", "fno", "p&l", "pnl")):
            return ClassifiedDocument("demat_trade_report", confidence=0.93)
        if _has_any(header_text, ("dividend",)):
            return ClassifiedDocument("dividend_report", confidence=0.88)
        return ClassifiedDocument("demat_holdings", confidence=0.86)
    if _has_any(header_text, ("capital gains", "stcgt", "ltcgt", "p&l", "pnl")):
        return ClassifiedDocument("demat_tax_report", confidence=0.86)
    if _has_any(header_text, ("holdings", "balance statement")):
        return ClassifiedDocument("demat_holdings", confidence=0.82)
    if _has_any(header_text, ("dividend",)):
        return ClassifiedDocument("dividend_report", confidence=0.84)

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

    # Let strong statement signatures win before demat/tax heuristics. Real bank
    # statements often contain merchants like Groww or words like dividend.
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

    if bank_hint and _has_any(
        header_text,
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
        header_text,
        ("account statement", "savings account", "current account", "passbook"),
    ):
        return ClassifiedDocument(
            "bank_statement",
            bank_hint=bank_hint,
            account_type_hint="bank_account",
            confidence=0.74,
            reason="bank_hint+account_statement_phrase",
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


def _header_excerpt(text: str, *, max_lines: int = 40, max_chars: int = 2500) -> str:
    selected: list[str] = []
    for raw_line in text.splitlines():
        normalized = " ".join(raw_line.lower().split())
        if any(
            marker in normalized
            for marker in (
                "txn date",
                "transaction details",
                "value date",
                "debit credit balance",
                "date narration",
                "date particulars",
                "date description",
            )
        ):
            break
        selected.append(raw_line)
        if len(selected) >= max_lines:
            break
    excerpt = "\n".join(selected)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars]
    return excerpt


def _bank_routing_excerpt(text: str, *, max_lines: int = 20, max_chars: int = 1200) -> str:
    selected: list[str] = []
    for raw_line in text.splitlines():
        normalized = " ".join(raw_line.lower().split())
        if any(
            marker in normalized
            for marker in (
                "txn date",
                "transaction details",
                "value date",
                "debit credit balance",
            )
        ):
            break
        selected.append(raw_line)
        if len(selected) >= max_lines:
            break
    excerpt = "\n".join(selected)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars]
    return excerpt


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
