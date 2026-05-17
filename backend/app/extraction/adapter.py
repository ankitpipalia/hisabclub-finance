from __future__ import annotations

from datetime import date
from typing import Any

from app.extraction.models import ExtractionSource, RawTransaction


def source_from_parser_context(*, parser_id: str, used_ocr: bool = False) -> ExtractionSource:
    parser = (parser_id or "").strip().lower()
    if "vision" in parser:
        return ExtractionSource.LLM_VISION
    if "llm" in parser:
        return ExtractionSource.LLM_TEXT
    if used_ocr:
        return ExtractionSource.OCR_LLM
    return ExtractionSource.TEMPLATE


def extracted_transaction_to_raw(
    txn: Any,
    *,
    parser_id: str,
    used_ocr: bool = False,
    default_page_number: int = 1,
) -> RawTransaction:
    txn_date = getattr(txn, "transaction_date", "")
    date_raw = _format_date(txn_date)
    direction = str(getattr(txn, "direction", "") or "")
    line_number = getattr(txn, "line_number", None)
    page_number = int(default_page_number or 1)
    char_offset = int(line_number or 0)
    evidence = {
        "date": date_raw,
        "posting_date": _format_date(getattr(txn, "posting_date", None)),
        "description": str(getattr(txn, "description", "") or ""),
        "amount": str(getattr(txn, "amount", "") or ""),
        "direction": direction,
        "reference_number": str(getattr(txn, "reference_number", "") or ""),
        "line_number": str(line_number or ""),
        "parser_id": parser_id,
    }
    return RawTransaction(
        date_raw=date_raw,
        description_raw=evidence["description"],
        amount_raw=evidence["amount"],
        balance_raw=None,
        txn_type_raw=direction,
        page_number=page_number,
        char_offset=char_offset,
        confidence=max(0.0, min(1.0, float(getattr(txn, "confidence", 0.0) or 0.0))),
        source=source_from_parser_context(parser_id=parser_id, used_ocr=used_ocr),
        source_evidence=evidence,
    )


def dict_to_raw_transaction(
    row: dict[str, Any],
    page_number: int = 1,
    source: ExtractionSource = ExtractionSource.TEMPLATE,
    confidence: float = 0.9,
) -> RawTransaction:
    return RawTransaction(
        date_raw=str(row.get("date") or row.get("transaction_date") or ""),
        description_raw=str(row.get("description") or row.get("narration") or ""),
        amount_raw=str(row.get("amount") or ""),
        balance_raw=str(row.get("balance") or "") if row.get("balance") is not None else None,
        txn_type_raw=str(row.get("type") or row.get("txn_type") or row.get("direction") or ""),
        page_number=int(row.get("page_number") or page_number or 1),
        char_offset=int(row.get("char_offset") or 0),
        confidence=max(0.0, min(1.0, float(row.get("confidence", confidence) or 0.0))),
        source=source,
        source_evidence={key: str(value) for key, value in row.items()},
    )


def _format_date(value: Any) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value or "")
