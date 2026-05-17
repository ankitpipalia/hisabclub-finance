"""LLM fallback parser with iterative chunk extraction and schema validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.llm.knowledge import StatementKnowledgeContext
from app.engines.llm.prompts import (
    STATEMENT_EXTRACTION_PROMPT_VERSION,
    build_statement_extraction_system_prompt,
    few_shot_messages,
)
from app.engines.llm.sanitizer import sanitize_for_llm
from app.engines.parser.amount_utils import (
    is_credit_indicator,
    parse_indian_amount,
    parse_indian_date,
)
from app.engines.parser.base import ExtractedStatement, ExtractedTransaction
from app.engines.parser.hints import normalize_bank_hint

logger = logging.getLogger(__name__)


class _LLMTransaction(BaseModel):
    date: str
    description: str
    amount: float
    direction: Literal["debit", "credit"]
    reference_number: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class _LLMStatementPayload(BaseModel):
    bank_name: str | None = None
    account_type: Literal["credit_card", "savings", "current", "unknown"] = "unknown"
    account_number_masked: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    transactions: list[_LLMTransaction] = Field(default_factory=list)


class _LLMColumnMap(BaseModel):
    date_col: int | None = None
    description_col: int | None = None
    debit_col: int | None = None
    credit_col: int | None = None
    amount_col: int | None = None
    direction_col: int | None = None
    reference_col: int | None = None


@dataclass(frozen=True)
class _Chunk:
    index: int
    total: int
    text: str


@dataclass(frozen=True)
class _ValidatedPayload:
    bank_name: str | None
    account_type: str
    account_number_masked: str | None
    statement_period_start: str | None
    statement_period_end: str | None
    opening_balance: float | None
    closing_balance: float | None
    transactions: list[_LLMTransaction]


async def llm_parse_statement(
    client: LLMClient,
    page_text: str,
    *,
    model: str | None = None,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    knowledge_context: StatementKnowledgeContext | None = None,
    table_rows: list[str] | None = None,
) -> ExtractedStatement | None:
    """Use iterative local-LLM extraction for unsupported statement layouts."""
    if table_rows:
        tier2_result = await _tier2_table_mapping_extract(
            client=client,
            model=model,
            bank_hint=bank_hint,
            account_type_hint=account_type_hint,
            table_rows=table_rows,
        )
        if tier2_result is not None and tier2_result.transactions:
            return tier2_result

    sanitized = sanitize_for_llm(page_text)
    chunks = _build_chunks(sanitized)
    if not chunks:
        return None

    context_text = knowledge_context.as_prompt_context() if knowledge_context else "none"
    prompt_examples = few_shot_messages(
        bank_hint=bank_hint,
        account_type_hint=account_type_hint,
        max_examples=2,
    )

    merged_transactions: list[ExtractedTransaction] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
    failed_empty_chunks: list[int] = []
    failed_schema_chunks: list[int] = []

    metadata_bank: str | None = None
    metadata_account_type: str | None = None
    metadata_account_masked: str | None = None
    metadata_period_start: date | None = None
    metadata_period_end: date | None = None
    metadata_opening_balance: float | None = None
    metadata_closing_balance: float | None = None

    for chunk in chunks:
        messages = [
            {"role": "system", "content": build_statement_extraction_system_prompt()},
            *prompt_examples,
            {
                "role": "user",
                "content": (
                    f"Prompt version: {STATEMENT_EXTRACTION_PROMPT_VERSION}\n"
                    f"Chunk: {chunk.index + 1}/{chunk.total}\n"
                    f"Bank hint: {bank_hint or 'none'}\n"
                    f"Account type hint: {account_type_hint or 'none'}\n"
                    f"Relevant customer context:\n{context_text}\n\n"
                    "Extract transactions from this chunk only:\n\n"
                    f"{chunk.text}"
                ),
            },
        ]
        payload = await client.chat_json(
            messages,
            schema=_statement_schema(),
            max_tokens=4096,
            temperature=0.0,
            timeout_sec=settings.llm_statement_extract_timeout_sec,
            max_attempts=settings.llm_statement_extract_max_attempts,
            model=model,
        )
        if not payload:
            failed_empty_chunks.append(chunk.index + 1)
            continue

        parsed = _validate_payload(payload)
        if parsed is None:
            failed_schema_chunks.append(chunk.index + 1)
            continue

        metadata_bank = metadata_bank or normalize_bank_hint(parsed.bank_name)
        metadata_account_type = metadata_account_type or parsed.account_type
        metadata_account_masked = metadata_account_masked or parsed.account_number_masked
        metadata_period_start = metadata_period_start or _parse_date(parsed.statement_period_start)
        metadata_period_end = metadata_period_end or _parse_date(parsed.statement_period_end)
        metadata_opening_balance = (
            metadata_opening_balance
            if metadata_opening_balance is not None
            else _safe_float(parsed.opening_balance)
        )
        metadata_closing_balance = (
            metadata_closing_balance
            if metadata_closing_balance is not None
            else _safe_float(parsed.closing_balance)
        )

        current_date: date | None = None
        for txn in parsed.transactions:
            txn_date = _parse_date(txn.date) or current_date
            if txn_date is None:
                continue
            current_date = txn_date

            amount = _safe_float(txn.amount)
            if amount is None or amount <= 0:
                continue

            description = str(txn.description or "").strip()
            if not description:
                continue

            key = (
                txn_date.isoformat(),
                txn.direction,
                int(round(amount * 100)),
                description[:90].upper(),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)

            merged_transactions.append(
                ExtractedTransaction(
                    transaction_date=txn_date,
                    posting_date=None,
                    description=description,
                    amount=amount,
                    direction=txn.direction,
                    reference_number=txn.reference_number,
                    confidence=max(0.0, min(1.0, _safe_float(txn.confidence) or 0.7)),
                )
            )

    if not merged_transactions:
        logger.warning("LLM iterative parser produced zero valid transactions")
        return None

    inferred_account_type = _normalize_account_type(
        account_type_hint=account_type_hint,
        extracted=metadata_account_type,
    )
    chunk_warnings = []
    failed_chunks = sorted(set(failed_empty_chunks + failed_schema_chunks))
    if failed_chunks:
        chunk_warnings.append(
            "LLM extraction partial: "
            f"{len(failed_chunks)}/{len(chunks)} chunks failed "
            f"(indices: {failed_chunks})"
        )

    return ExtractedStatement(
        bank_name=metadata_bank or bank_hint or "Unknown",
        account_type=inferred_account_type,
        account_number_masked=metadata_account_masked,
        statement_period_start=metadata_period_start,
        statement_period_end=metadata_period_end,
        opening_balance=metadata_opening_balance,
        closing_balance=metadata_closing_balance,
        transactions=merged_transactions,
        parser_id="llm_fallback_iterative",
        warnings=[
            "Parsed by LLM fallback (iterative chunk mode).",
            f"Prompt version: {STATEMENT_EXTRACTION_PROMPT_VERSION}",
            *chunk_warnings,
        ],
        llm_chunk_errors={
            "total": len(chunks),
            "failed_empty": failed_empty_chunks,
            "failed_schema": failed_schema_chunks,
        }
        if failed_chunks
        else None,
    )


async def _tier2_table_mapping_extract(
    *,
    client: LLMClient,
    model: str | None,
    bank_hint: str | None,
    account_type_hint: str | None,
    table_rows: list[str],
) -> ExtractedStatement | None:
    table_chunks = _build_table_row_chunks(table_rows)
    if not table_chunks:
        return None

    mapping = await _infer_table_column_mapping(
        client=client,
        model=model,
        bank_hint=bank_hint,
        account_type_hint=account_type_hint,
        sample_rows=table_chunks[0],
    )
    if mapping is None:
        return None
    if mapping.date_col is None or mapping.description_col is None:
        return None
    if mapping.debit_col is None and mapping.credit_col is None and mapping.amount_col is None:
        return None

    transactions: list[ExtractedTransaction] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
    last_date: date | None = None
    for chunk in table_chunks:
        for line in chunk:
            cols = _split_table_row(line)
            txn = _map_row_to_transaction(cols, mapping, last_date=last_date)
            if txn is None:
                continue
            last_date = txn.transaction_date
            key = (
                txn.transaction_date.isoformat(),
                txn.direction,
                int(round(float(txn.amount) * 100)),
                txn.description[:90].upper(),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            transactions.append(txn)

    if not transactions:
        return None

    metadata = await _tier2_extract_metadata(
        client=client,
        model=model,
        bank_hint=bank_hint,
        account_type_hint=account_type_hint,
        sample_rows=table_rows[:60],
    )

    return ExtractedStatement(
        bank_name=normalize_bank_hint(metadata.bank_name or bank_hint) or bank_hint or "Unknown",
        account_type=_normalize_account_type(
            account_type_hint=account_type_hint,
            extracted=metadata.account_type,
        ),
        account_number_masked=metadata.account_number_masked,
        statement_period_start=metadata.statement_period_start,
        statement_period_end=metadata.statement_period_end,
        opening_balance=metadata.opening_balance,
        closing_balance=metadata.closing_balance,
        transactions=transactions,
        parser_id="llm_tier2_column_map",
        warnings=[
            "Parsed by tier-2 table mapping (deterministic rows + LLM column map).",
            f"Prompt version: {STATEMENT_EXTRACTION_PROMPT_VERSION}",
        ],
    )


@dataclass(frozen=True)
class _Tier2Metadata:
    bank_name: str | None
    account_type: str | None
    account_number_masked: str | None
    statement_period_start: date | None
    statement_period_end: date | None
    opening_balance: float | None
    closing_balance: float | None


async def _tier2_extract_metadata(
    *,
    client: LLMClient,
    model: str | None,
    bank_hint: str | None,
    account_type_hint: str | None,
    sample_rows: list[str],
) -> _Tier2Metadata:
    preview = "\n".join(sample_rows[:20])
    payload = await client.chat_json(
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract statement metadata from table headers and first rows. "
                    "Return strict JSON only. Never guess values not present in the text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Bank hint: {bank_hint or 'none'}\n"
                    f"Account type hint: {account_type_hint or 'none'}\n"
                    "Extract these fields from the table header/first rows only:\n"
                    '{"bank_name":str|null,"account_type":"credit_card|savings|current|null",'
                    '"account_number_masked":str|null,'
                    '"statement_period_start":str|null,"statement_period_end":str|null,'
                    '"opening_balance":number|null,"closing_balance":number|null}\n\n'
                    f"{preview}"
                ),
            },
        ],
        schema={
            "type": "object",
            "properties": {
                "bank_name": {"type": ["string", "null"]},
                "account_type": {"type": ["string", "null"]},
                "account_number_masked": {"type": ["string", "null"]},
                "statement_period_start": {"type": ["string", "null"]},
                "statement_period_end": {"type": ["string", "null"]},
                "opening_balance": {"type": ["number", "null"]},
                "closing_balance": {"type": ["number", "null"]},
            },
            "required": [],
            "additionalProperties": False,
        },
        max_tokens=220,
        temperature=0.0,
        timeout_sec=settings.llm_table_map_timeout_sec,
        max_attempts=settings.llm_table_map_max_attempts,
        model=model,
    )
    if not payload:
        return _Tier2Metadata(
            bank_name=None,
            account_type=None,
            account_number_masked=None,
            statement_period_start=None,
            statement_period_end=None,
            opening_balance=None,
            closing_balance=None,
        )
    try:
        bn = _string_or_none(payload.get("bank_name"))
        at = _string_or_none(payload.get("account_type"))
        normalized_at = _normalize_account_type(account_type_hint=account_type_hint, extracted=at)
        if at == "unknown":
            normalized_at = None
        return _Tier2Metadata(
            bank_name=bn,
            account_type=normalized_at if at and at != "unknown" else None,
            account_number_masked=_string_or_none(payload.get("account_number_masked")),
            statement_period_start=_parse_date(_string_or_none(payload.get("statement_period_start"))),
            statement_period_end=_parse_date(_string_or_none(payload.get("statement_period_end"))),
            opening_balance=_safe_float(payload.get("opening_balance")),
            closing_balance=_safe_float(payload.get("closing_balance")),
        )
    except Exception:
        return _Tier2Metadata(
            bank_name=None,
            account_type=None,
            account_number_masked=None,
            statement_period_start=None,
            statement_period_end=None,
            opening_balance=None,
            closing_balance=None,
        )


async def _infer_table_column_mapping(
    *,
    client: LLMClient,
    model: str | None,
    bank_hint: str | None,
    account_type_hint: str | None,
    sample_rows: list[str],
) -> _LLMColumnMap | None:
    preview = "\n".join(sample_rows[:60])
    payload = await client.chat_json(
        messages=[
            {
                "role": "system",
                "content": (
                    "You map statement table columns to canonical schema. "
                    "Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Bank hint: {bank_hint or 'none'}\n"
                    f"Account type hint: {account_type_hint or 'none'}\n"
                    "Given these pipe-delimited table rows, return column indices:\n"
                    '{"date_col":int|null,"description_col":int|null,"debit_col":int|null,'
                    '"credit_col":int|null,"amount_col":int|null,"direction_col":int|null,'
                    '"reference_col":int|null}\n\n'
                    f"{preview}"
                ),
            },
        ],
        schema={
            "type": "object",
            "properties": {
                "date_col": {"type": ["integer", "null"]},
                "description_col": {"type": ["integer", "null"]},
                "debit_col": {"type": ["integer", "null"]},
                "credit_col": {"type": ["integer", "null"]},
                "amount_col": {"type": ["integer", "null"]},
                "direction_col": {"type": ["integer", "null"]},
                "reference_col": {"type": ["integer", "null"]},
            },
            "required": ["date_col", "description_col"],
            "additionalProperties": False,
        },
        max_tokens=220,
        temperature=0.0,
        timeout_sec=settings.llm_table_map_timeout_sec,
        max_attempts=settings.llm_table_map_max_attempts,
        model=model,
    )
    if not payload:
        return None
    try:
        return _LLMColumnMap.model_validate(payload)
    except ValidationError:
        return None


def _build_table_row_chunks(
    rows: list[str],
    *,
    chunk_size: int = 120,
    overlap: int = 8,
) -> list[list[str]]:
    # Skip obvious header-only rows to keep deterministic parser focused on line items.
    filtered = [line for line in rows if line and not _is_probable_header_row(line)]
    if not filtered:
        return []
    chunks: list[list[str]] = []
    start = 0
    while start < len(filtered):
        end = min(len(filtered), start + chunk_size)
        chunks.append(filtered[start:end])
        if end >= len(filtered):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.split("|")]


def _map_row_to_transaction(
    cols: list[str],
    mapping: _LLMColumnMap,
    *,
    last_date: date | None,
) -> ExtractedTransaction | None:
    date_value = _cell(cols, mapping.date_col)
    parsed_date = parse_indian_date(date_value) if date_value else None
    txn_date = parsed_date or last_date
    if txn_date is None:
        return None

    description = _cell(cols, mapping.description_col)
    if not description:
        return None

    amount: float | None = None
    direction: str | None = None
    debit_val = parse_indian_amount(_cell(cols, mapping.debit_col) or "")
    credit_val = parse_indian_amount(_cell(cols, mapping.credit_col) or "")
    amount_val = parse_indian_amount(_cell(cols, mapping.amount_col) or "")

    if debit_val and debit_val > 0:
        amount = abs(debit_val)
        direction = "debit"
    elif credit_val and credit_val > 0:
        amount = abs(credit_val)
        direction = "credit"
    elif amount_val and amount_val > 0:
        dir_text = _cell(cols, mapping.direction_col) or ""
        indicator = is_credit_indicator(dir_text) if dir_text else None
        if indicator is None:
            upper_line = " ".join(cols).upper()
            if " CR" in upper_line or " CREDIT" in upper_line:
                indicator = True
            elif " DR" in upper_line or " DEBIT" in upper_line:
                indicator = False
        if indicator is None:
            return None
        direction = "credit" if indicator else "debit"
    if amount is None or amount <= 0 or direction is None:
        return None

    return ExtractedTransaction(
        transaction_date=txn_date,
        posting_date=None,
        description=description,
        amount=amount,
        direction=direction,
        reference_number=_cell(cols, mapping.reference_col),
        confidence=0.88,
    )


def _cell(cols: list[str], index: int | None) -> str | None:
    if index is None:
        return None
    if index < 0 or index >= len(cols):
        return None
    value = cols[index].strip()
    return value or None


def _is_probable_header_row(line: str) -> bool:
    upper = line.upper()
    tokens = ("DATE", "DESCRIPTION", "PARTICULARS", "DEBIT", "CREDIT", "BALANCE")
    return sum(1 for token in tokens if token in upper) >= 2


def _build_chunks(text: str) -> list[_Chunk]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    max_chars = max(1000, settings.llm_iterative_chunk_chars)
    overlap = max(0, settings.llm_iterative_overlap_lines)
    max_chunks = max(1, settings.llm_max_chunk_count)

    chunks: list[str] = []
    start = 0
    while start < len(lines) and len(chunks) < max_chunks:
        cur: list[str] = []
        char_count = 0
        idx = start
        while idx < len(lines):
            next_line = lines[idx]
            projected = char_count + len(next_line) + 1
            if cur and projected > max_chars:
                break
            cur.append(next_line)
            char_count = projected
            idx += 1
        if not cur:
            cur = [lines[start]]
            idx = start + 1
        chunks.append("\n".join(cur))
        if idx >= len(lines):
            break
        start = max(start + 1, idx - overlap)

    total = len(chunks)
    return [_Chunk(index=i, total=total, text=chunk) for i, chunk in enumerate(chunks)]


def _statement_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "bank_name": {"type": ["string", "null"]},
            "account_type": {"type": "string"},
            "account_number_masked": {"type": ["string", "null"]},
            "statement_period_start": {"type": ["string", "null"]},
            "statement_period_end": {"type": ["string", "null"]},
            "opening_balance": {"type": ["number", "null"]},
            "closing_balance": {"type": ["number", "null"]},
            "transactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "description": {"type": "string"},
                        "amount": {"type": "number"},
                        "direction": {"type": "string"},
                        "reference_number": {"type": ["string", "null"]},
                        "confidence": {"type": ["number", "null"]},
                    },
                    "required": ["date", "description", "amount", "direction"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["account_type", "transactions"],
        "additionalProperties": False,
    }


def _validate_payload(payload: dict) -> _LLMStatementPayload | None:
    normalized = _normalize_payload(payload)
    if normalized is None:
        return None
    try:
        return _LLMStatementPayload.model_validate(
            {
                "bank_name": normalized.bank_name,
                "account_type": normalized.account_type,
                "account_number_masked": normalized.account_number_masked,
                "statement_period_start": normalized.statement_period_start,
                "statement_period_end": normalized.statement_period_end,
                "opening_balance": normalized.opening_balance,
                "closing_balance": normalized.closing_balance,
                "transactions": [txn.model_dump() for txn in normalized.transactions],
            }
        )
    except ValidationError as exc:
        logger.warning("LLM payload schema validation failed: %s", exc.errors()[:2])
        return None


def _normalize_payload(payload: dict) -> _ValidatedPayload | None:
    if not isinstance(payload, dict):
        return None

    account_type = _normalize_account_type(
        account_type_hint=None,
        extracted=str(payload.get("account_type") or "unknown"),
    )
    opening_balance = _safe_float(payload.get("opening_balance"))
    closing_balance = _safe_float(payload.get("closing_balance"))

    raw_transactions = payload.get("transactions") or []
    if not isinstance(raw_transactions, list):
        raw_transactions = []

    transactions: list[_LLMTransaction] = []
    for raw_txn in raw_transactions:
        normalized_txn = _normalize_llm_transaction(raw_txn)
        if normalized_txn is not None:
            transactions.append(normalized_txn)

    return _ValidatedPayload(
        bank_name=normalize_bank_hint(payload.get("bank_name")),
        account_type=account_type,
        account_number_masked=_string_or_none(payload.get("account_number_masked")),
        statement_period_start=_normalized_date_string(payload.get("statement_period_start")),
        statement_period_end=_normalized_date_string(payload.get("statement_period_end")),
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        transactions=transactions,
    )


def _normalize_llm_transaction(payload: object) -> _LLMTransaction | None:
    if not isinstance(payload, dict):
        return None

    description = " ".join(str(payload.get("description") or "").split())
    if not description:
        return None

    parsed_date = _parse_date(_string_or_none(payload.get("date")))
    if parsed_date is None:
        return None

    amount = _coerce_amount(payload.get("amount"))
    if amount is None or amount <= 0:
        return None

    direction = _coerce_direction(payload.get("direction"), description)
    if direction is None:
        return None

    confidence = _safe_float(payload.get("confidence"))
    return _LLMTransaction(
        date=parsed_date.isoformat(),
        description=description,
        amount=amount,
        direction=direction,
        reference_number=_string_or_none(payload.get("reference_number")),
        confidence=max(0.0, min(1.0, confidence if confidence is not None else 0.7)),
    )


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    parsed = parse_indian_date(val)
    if parsed is not None:
        return parsed
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            if fmt == "%Y-%m-%d":
                return date.fromisoformat(val)
            return datetime.strptime(val, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _coerce_amount(val: object) -> float | None:
    if isinstance(val, str):
        parsed = parse_indian_amount(val)
        return abs(parsed) if parsed is not None else None
    numeric = _safe_float(val)
    return abs(numeric) if numeric is not None else None


def _coerce_direction(val: object, description: str) -> str | None:
    normalized = str(val or "").strip().lower()
    if normalized in {"credit", "debit"}:
        return normalized
    indicator = is_credit_indicator(str(val or ""))
    if indicator is not None:
        return "credit" if indicator else "debit"
    upper = description.upper()
    if any(token in upper for token in (" CR", " CREDIT", "DEPOSIT", "PAYMENT RECEIVED")):
        return "credit"
    if any(token in upper for token in (" DR", " DEBIT", "WITHDRAW", "PURCHASE", "SPENT")):
        return "debit"
    return None


def _string_or_none(val: object) -> str | None:
    text = str(val or "").strip()
    return text or None


def _normalized_date_string(val: object) -> str | None:
    parsed = _parse_date(_string_or_none(val))
    return parsed.isoformat() if parsed is not None else None


def _normalize_account_type(
    *,
    account_type_hint: str | None,
    extracted: str | None,
) -> str:
    normalized = (extracted or "").strip().lower()
    if account_type_hint == "credit_card":
        return "credit_card"
    if account_type_hint == "bank_account":
        return "savings" if normalized == "credit_card" else (normalized or "savings")
    if normalized not in {"credit_card", "savings", "current"}:
        return "savings"
    return normalized
