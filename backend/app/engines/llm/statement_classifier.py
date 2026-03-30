"""LLM-assisted bank/account classification for ambiguous statement PDFs."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.llm.knowledge import StatementKnowledgeContext
from app.engines.llm.prompts import (
    STATEMENT_CLASSIFICATION_PROMPT_VERSION,
    build_statement_classification_system_prompt,
)
from app.engines.llm.sanitizer import sanitize_for_llm
from app.engines.parser.hints import normalize_bank_hint


@dataclass
class StatementClassification:
    bank_name: str | None
    account_type: str | None
    confidence: float
    reason: str | None = None


async def llm_classify_statement(
    client: LLMClient,
    page_text: str,
    *,
    model: str | None = None,
    knowledge_context: StatementKnowledgeContext | None = None,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
) -> StatementClassification | None:
    excerpt = sanitize_for_llm(page_text[:8000])
    context_text = knowledge_context.as_prompt_context() if knowledge_context else ""
    messages = [
        {
            "role": "system",
            "content": build_statement_classification_system_prompt(),
        },
        {
            "role": "user",
            "content": (
                f"Prompt version: {STATEMENT_CLASSIFICATION_PROMPT_VERSION}\n"
                f"User hint bank: {bank_hint or 'none'}\n"
                f"User hint account type: {account_type_hint or 'none'}\n"
                f"Retrieved customer context:\n{context_text or 'none'}\n\n"
                f"Current statement text:\n{excerpt}"
            ),
        },
    ]
    payload = await client.chat_json(
        messages,
        model=model,
        max_tokens=260,
        timeout_sec=settings.llm_statement_classify_timeout_sec,
        max_attempts=settings.llm_statement_classify_max_attempts,
        schema={
            "type": "object",
            "properties": {
                "bank_name": {"type": ["string", "null"]},
                "account_type": {"type": "string"},
                "confidence": {"type": "number"},
                "reason": {"type": ["string", "null"]},
            },
            "required": ["bank_name", "account_type", "confidence"],
            "additionalProperties": False,
        },
    )
    if not payload:
        return None

    account_type = str(payload.get("account_type", "")).strip().lower()
    if account_type not in {"credit_card", "savings", "current"}:
        account_type = None
    bank_name = normalize_bank_hint(payload.get("bank_name"))
    try:
        confidence = float(payload.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(payload.get("reason", "")).strip()[:220] or None

    if not bank_name and not account_type:
        return None
    return StatementClassification(
        bank_name=bank_name,
        account_type=account_type,
        confidence=confidence,
        reason=reason,
    )
