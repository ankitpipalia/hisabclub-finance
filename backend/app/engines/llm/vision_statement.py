"""Vision-first statement extraction for page-image capable local LLMs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.parser.amount_utils import parse_indian_amount, parse_indian_date
from app.engines.parser.base import ExtractedStatement, ExtractedTransaction
from app.engines.parser.hints import normalize_bank_hint
from app.engines.parser.ocr import render_pdf_pages

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisionExtractionResult:
    statement: ExtractedStatement | None
    warnings: list[str]


async def llm_parse_statement_from_page_images(
    client: LLMClient,
    pdf_bytes: bytes,
    *,
    model: str | None = None,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
) -> VisionExtractionResult:
    page_limit = max(1, int(settings.llm_vision_page_limit))
    rendered_pages = render_pdf_pages(
        pdf_bytes,
        list(range(page_limit)),
        dpi=max(96, int(settings.llm_vision_render_dpi)),
    )
    if not rendered_pages:
        return VisionExtractionResult(statement=None, warnings=["Vision extraction could not render PDF pages."])

    transactions: list[ExtractedTransaction] = []
    seen_keys: set[tuple[str, int, str, str]] = set()
    warnings: list[str] = []

    bank_name: str | None = normalize_bank_hint(bank_hint)
    account_type: str | None = None
    account_number_masked: str | None = None
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None

    for page_number, image_bytes in rendered_pages:
        payload = await client.chat_vision_json(
            _build_page_prompt(
                page_number=page_number + 1,
                bank_hint=bank_hint,
                account_type_hint=account_type_hint,
            ),
            image_bytes=image_bytes,
            schema=_vision_statement_schema(),
            max_tokens=3200,
            temperature=0.0,
            timeout_sec=settings.llm_statement_extract_timeout_sec,
            max_attempts=settings.llm_statement_extract_max_attempts,
            model=model,
        )
        if not payload:
            warnings.append(f"Vision extraction returned no usable JSON for page {page_number + 1}.")
            continue

        bank_name = bank_name or normalize_bank_hint(_safe_string(payload.get("bank_name")))
        account_type = account_type or _normalize_account_type(
            _safe_string(payload.get("account_type")),
            account_type_hint=account_type_hint,
        )
        account_number_masked = account_number_masked or _safe_string(
            payload.get("account_number_masked")
        )
        statement_period_start = statement_period_start or _safe_date(
            payload.get("statement_period_start")
        )
        statement_period_end = statement_period_end or _safe_date(payload.get("statement_period_end"))
        opening_balance = opening_balance if opening_balance is not None else _safe_amount(
            payload.get("opening_balance")
        )
        closing_balance = closing_balance if closing_balance is not None else _safe_amount(
            payload.get("closing_balance")
        )

        raw_txns = payload.get("transactions")
        if not isinstance(raw_txns, list):
            continue

        for raw in raw_txns:
            if not isinstance(raw, dict):
                continue
            txn = _to_transaction(raw)
            if txn is None:
                continue
            key = (
                txn.transaction_date.isoformat(),
                int(round(float(txn.amount) * 100)),
                txn.direction,
                txn.description[:90].upper(),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            transactions.append(txn)

    if not transactions:
        return VisionExtractionResult(statement=None, warnings=warnings or ["Vision extraction produced zero valid transactions."])

    return VisionExtractionResult(
        statement=ExtractedStatement(
            bank_name=bank_name or bank_hint or "Unknown",
            account_type=_normalize_account_type(account_type, account_type_hint=account_type_hint),
            account_number_masked=account_number_masked,
            statement_period_start=statement_period_start,
            statement_period_end=statement_period_end,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            transactions=transactions,
            parser_id="llm_vision_page_extract",
            warnings=[
                "Parsed via local vision-capable LLM from rendered statement pages.",
                f"Processed up to {page_limit} page(s).",
            ],
        ),
        warnings=warnings,
    )


def _build_page_prompt(*, page_number: int, bank_hint: str | None, account_type_hint: str | None) -> str:
    return (
        "You are extracting data from one page of an Indian bank or credit-card statement. "
        "Return strict JSON only. Never hallucinate hidden rows. "
        "Do not emit markdown.\n"
        f"Page number: {page_number}\n"
        f"Bank hint: {bank_hint or 'none'}\n"
        f"Account type hint: {account_type_hint or 'none'}\n"
        "Rules:\n"
        "- Extract only real transaction rows from this page.\n"
        "- Ignore column headers, opening balance, closing balance, totals, summary boxes, reward blocks.\n"
        '- direction must be exactly "debit" or "credit".\n'
        "- amount must be positive INR numeric without commas.\n"
        "- preserve payment references such as UPI/UTR/IMPS/NEFT/RTGS when visible.\n"
        "- if a field is unclear, return null instead of inventing it.\n"
        "- if the page contains no transactions, return an empty transactions array.\n"
    )


def _vision_statement_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "bank_name": {"type": ["string", "null"]},
            "account_type": {"type": ["string", "null"]},
            "account_number_masked": {"type": ["string", "null"]},
            "statement_period_start": {"type": ["string", "null"]},
            "statement_period_end": {"type": ["string", "null"]},
            "opening_balance": {"type": ["number", "string", "null"]},
            "closing_balance": {"type": ["number", "string", "null"]},
            "transactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                        "amount": {"type": ["number", "string", "null"]},
                        "direction": {"type": ["string", "null"]},
                        "reference_number": {"type": ["string", "null"]},
                        "confidence": {"type": ["number", "null"]},
                    },
                    "required": ["date", "description", "amount", "direction"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["transactions"],
        "additionalProperties": False,
    }


def _to_transaction(raw: dict) -> ExtractedTransaction | None:
    txn_date = _safe_date(
        raw.get("date")
        or raw.get("txn_date")
        or raw.get("tran_date")
        or raw.get("transaction_date")
        or raw.get("value_date")
    )
    description = _safe_string(
        raw.get("description")
        or raw.get("narration")
        or raw.get("particulars")
        or raw.get("details")
    )
    amount = _safe_amount(raw.get("amount"))
    direction = _normalize_direction(_safe_string(raw.get("direction")))
    if amount is None:
        debit_amount = _safe_amount(
            raw.get("debit_amount")
            or raw.get("debit")
            or raw.get("withdrawal")
            or raw.get("withdrawal_dr")
            or raw.get("debit_dr")
        )
        credit_amount = _safe_amount(
            raw.get("credit_amount")
            or raw.get("credit")
            or raw.get("deposit")
            or raw.get("deposit_cr")
            or raw.get("credit_cr")
        )
        if debit_amount and debit_amount > 0:
            amount = debit_amount
            direction = "debit"
        elif credit_amount and credit_amount > 0:
            amount = credit_amount
            direction = "credit"
    if txn_date is None or not description or amount is None or amount <= 0 or direction is None:
        return None
    confidence = _safe_float(raw.get("confidence"))
    if confidence is None:
        confidence = _default_transaction_confidence(
            description=description,
            reference_number=_safe_string(
                raw.get("reference_number")
                or raw.get("reference")
                or raw.get("utr")
                or raw.get("rrn")
            ),
            amount=amount,
        )
    # Vision OCR has materially higher hallucination rate than text extraction;
    # apply the configured discount so downstream review-gates fire earlier.
    confidence = _apply_vision_confidence_discount(confidence)
    return ExtractedTransaction(
        transaction_date=txn_date,
        posting_date=None,
        description=description,
        amount=amount,
        direction=direction,
        reference_number=_safe_string(
            raw.get("reference_number") or raw.get("reference") or raw.get("utr") or raw.get("rrn")
        ),
        confidence=max(0.0, min(1.0, confidence)),
    )


def _apply_vision_confidence_discount(confidence: float) -> float:
    from app.config import settings

    multiplier = max(0.0, min(1.0, settings.vision_confidence_multiplier))
    return confidence * multiplier


def _default_transaction_confidence(
    *,
    description: str,
    reference_number: str | None,
    amount: float,
) -> float:
    score = 0.84
    if len(description.strip()) >= 8:
        score += 0.03
    if reference_number:
        score += 0.03
    if 0 < float(amount) <= 1_000_000:
        score += 0.02
    return min(score, 0.94)


def _normalize_account_type(value: str | None, *, account_type_hint: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"credit_card", "savings", "current"}:
        return normalized
    if account_type_hint == "credit_card":
        return "credit_card"
    if account_type_hint in {"bank_account", "savings", "current"}:
        return "savings" if account_type_hint == "bank_account" else account_type_hint
    return "savings"


def _normalize_direction(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"dr", "d", "debit"}:
        return "debit"
    if normalized in {"cr", "c", "credit"}:
        return "credit"
    return None


def _safe_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_amount(value: object) -> float | None:
    if value is None:
        return None
    parsed = parse_indian_amount(str(value))
    if parsed is not None:
        return parsed
    return _safe_float(value)


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_date(value: object) -> date | None:
    if value is None:
        return None
    return parse_indian_date(str(value))
