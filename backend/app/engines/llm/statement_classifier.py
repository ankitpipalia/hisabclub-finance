"""LLM-assisted bank/account classification for ambiguous statement PDFs."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.engines.llm.client import LLMClient
from app.engines.llm.knowledge import StatementKnowledgeContext
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
    knowledge_context: StatementKnowledgeContext | None = None,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
) -> StatementClassification | None:
    excerpt = sanitize_for_llm(page_text[:8000])
    context_text = knowledge_context.as_prompt_context() if knowledge_context else ""
    messages = [
        {
            "role": "system",
            "content": (
                "You classify Indian financial statements. "
                "Use the current document text as the primary signal. "
                "Retrieved customer context is supportive only and must never override the current document. "
                'Return strict JSON: {"bank_name":"string|null","account_type":"credit_card|savings|current|unknown","confidence":0..1,"reason":"<=25 words"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"User hint bank: {bank_hint or 'none'}\n"
                f"User hint account type: {account_type_hint or 'none'}\n"
                f"Retrieved customer context:\n{context_text or 'none'}\n\n"
                f"Current statement text:\n{excerpt}"
            ),
        },
    ]
    response = await client.chat(
        messages,
        max_tokens=220,
        temperature=0.0,
        timeout_sec=25.0,
        max_attempts=1,
    )
    if not response:
        return None
    try:
        payload = json.loads(_clean_json(response))
    except json.JSONDecodeError:
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


def _clean_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.replace("json", "", 1).strip()
