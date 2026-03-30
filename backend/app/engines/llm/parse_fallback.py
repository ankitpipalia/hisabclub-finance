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
            max_tokens=2600,
            temperature=0.0,
            timeout_sec=55.0,
            max_attempts=2,
            model=model,
        )
        if not payload:
            continue

        parsed = _validate_payload(payload)
        if parsed is None:
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
        ],
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

    return ExtractedStatement(
        bank_name=normalize_bank_hint(bank_hint) or bank_hint or "Unknown",
        account_type=_normalize_account_type(
            account_type_hint=account_type_hint,
            extracted="credit_card" if account_type_hint == "credit_card" else "savings",
        ),
        account_number_masked=None,
        statement_period_start=None,
        statement_period_end=None,
        opening_balance=None,
        closing_balance=None,
        transactions=transactions,
        parser_id="llm_tier2_column_map",
        warnings=[
            "Parsed by tier-2 table mapping (deterministic rows + LLM column map).",
            f"Prompt version: {STATEMENT_EXTRACTION_PROMPT_VERSION}",
        ],
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
        timeout_sec=30.0,
        max_attempts=2,
        model=model,
    )
    if not payload:
        return None
    try:
        return _LLMColumnMap.model_validate(payload)
    except ValidationError:
        return None


def _build_table_row_chunks(rows: list[str], *, chunk_size: int = 120, overlap: int = 8) -> list[list[str]]:
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
        amount = abs(amount_val)
        dir_text = _cell(cols, mapping.direction_col) or ""
        indicator = is_credit_indicator(dir_text) if dir_text else None
        if indicator is None:
            upper_line = " ".join(cols).upper()
            if " CR" in upper_line or " CREDIT" in upper_line:
                indicator = True
            elif " DR" in upper_line or " DEBIT" in upper_line:
                indicator = False
        direction = "credit" if indicator is True else "debit"
    if amount is None or amount <= 0 or direction is None:
        return None

    return ExtractedTransaction(
        transaction_date=txn_date,
        posting_date=None,
        description=description,
        amount=amount,
        direction=direction,
        reference_number=_cell(cols, mapping.reference_col),
        confidence=0.9,
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
    try:
        return _LLMStatementPayload.model_validate(payload)
    except ValidationError as exc:
        logger.warning("LLM payload schema validation failed: %s", exc.errors()[:2])
        return None


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
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
