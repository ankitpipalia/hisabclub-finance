"""LLM fallback classifier for uploaded PDFs in auto-detect mode."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.engines.intake.doc_classifier import ClassifiedDocument, normalize_doc_type_hint
from app.engines.llm.client import LLMClient
from app.engines.llm.prompts import (
    DOCUMENT_CLASSIFICATION_PROMPT_VERSION,
    build_document_classification_system_prompt,
)
from app.engines.llm.sanitizer import sanitize_for_llm
from app.engines.parser.hints import normalize_bank_hint


@dataclass
class LLMDocumentClassification:
    doc_type: str
    bank_hint: str | None
    account_type_hint: str | None
    confidence: float
    reason: str | None = None


async def llm_classify_uploaded_document(
    client: LLMClient,
    *,
    filename: str,
    extracted_text: str,
    deterministic: ClassifiedDocument | None = None,
    model: str | None = None,
) -> LLMDocumentClassification | None:
    text_excerpt = sanitize_for_llm((extracted_text or "")[:12000])
    filename_excerpt = sanitize_for_llm(filename[:300])
    base_doc_type = deterministic.doc_type if deterministic else "unknown_pdf"
    base_bank = deterministic.bank_hint if deterministic else None
    base_account = deterministic.account_type_hint if deterministic else None
    base_confidence = deterministic.confidence if deterministic else 0.0
    base_reason = deterministic.reason if deterministic else None

    messages = [
        {
            "role": "system",
            "content": build_document_classification_system_prompt(),
        },
        {
            "role": "user",
            "content": (
                f"Prompt version: {DOCUMENT_CLASSIFICATION_PROMPT_VERSION}\n"
                f"Filename: {filename_excerpt}\n"
                f"Deterministic classifier: doc_type={base_doc_type}, bank={base_bank or 'none'}, "
                f"account={base_account or 'none'}, confidence={base_confidence:.2f}, reason={base_reason or 'none'}\n\n"
                f"Document text excerpt:\n{text_excerpt or '[no_text]'}"
            ),
        },
    ]

    payload = await client.chat_json(
        messages,
        model=model,
        max_tokens=280,
        timeout_sec=settings.llm_statement_classify_timeout_sec,
        max_attempts=settings.llm_statement_classify_max_attempts,
        schema={
            "type": "object",
            "properties": {
                "doc_type": {"type": "string"},
                "bank_hint": {"type": ["string", "null"]},
                "account_type_hint": {"type": ["string", "null"]},
                "confidence": {"type": "number"},
                "reason": {"type": ["string", "null"]},
            },
            "required": ["doc_type", "bank_hint", "account_type_hint", "confidence"],
            "additionalProperties": False,
        },
    )
    if not payload:
        return None

    doc_type = normalize_doc_type_hint(payload.get("doc_type"))
    if not doc_type:
        doc_type = "unknown_pdf"
    bank_hint = normalize_bank_hint(payload.get("bank_hint"))
    account_type_raw = str(payload.get("account_type_hint", "")).strip().lower()
    account_type_hint: str | None
    if account_type_raw in {"credit_card"}:
        account_type_hint = "credit_card"
    elif account_type_raw in {"bank_account", "savings", "current"}:
        account_type_hint = "bank_account"
    else:
        account_type_hint = None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(payload.get("reason", "")).strip()[:220] or None

    return LLMDocumentClassification(
        doc_type=doc_type,
        bank_hint=bank_hint,
        account_type_hint=account_type_hint,
        confidence=confidence,
        reason=reason,
    )

