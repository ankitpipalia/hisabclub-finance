"""LLM helper for identifying internal transfers / credit card bill payments."""

from __future__ import annotations

import json
import logging

from app.engines.llm.client import LLMClient
from app.engines.llm.sanitizer import sanitize_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a banking transaction classifier.

Decide if a transaction is MOST LIKELY an internal transfer, especially a credit-card bill payment.

Return strict JSON:
{
  "is_credit_card_payment": true or false,
  "confidence": number between 0 and 1,
  "reason": "short reason"
}

Rules:
- Prefer true for self-transfer bill payments (IMPS/NEFT/RTGS/UPI transfer,
  tele transfer, card-payment references).
- Prefer false for salary, cashback, merchant refunds, or external third-party receipts.
- Output JSON only.
"""


async def llm_is_credit_card_payment(
    client: LLMClient,
    description: str,
    direction: str,
    account_type: str | None,
    bank_name: str | None,
    amount: float,
) -> dict | None:
    sanitized_desc = sanitize_for_llm(description)
    prompt = (
        f"Description: {sanitized_desc}\n"
        f"Direction: {direction}\n"
        f"Account Type: {account_type or 'unknown'}\n"
        f"Bank: {bank_name or 'unknown'}\n"
        f"Amount: {amount}\n"
    )
    response = await client.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=200,
        temperature=0.0,
    )
    if not response:
        return None

    try:
        parsed = json.loads(response)
    except Exception:
        logger.warning("transfer_classifier non-JSON response: %s", response[:200])
        return None

    if not isinstance(parsed, dict):
        return None
    if "is_credit_card_payment" not in parsed:
        return None

    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    return {
        "is_credit_card_payment": bool(parsed.get("is_credit_card_payment")),
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(parsed.get("reason", "")).strip()[:200],
    }
