"""LLM merchant cleanup — normalizes raw merchant descriptions and suggests categories."""

from __future__ import annotations

import json
import logging

from app.engines.llm.client import LLMClient
from app.engines.llm.sanitizer import sanitize_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial transaction analyst. Given a raw merchant description from a bank statement, do two things:
1. Clean up the merchant name to a human-friendly form (e.g. "SWIGGY DELIV ORDER 12345" -> "Swiggy")
2. Suggest the most likely spending category

Return ONLY a JSON object:
{
  "merchant_name": "cleaned merchant name",
  "category": "category name or null"
}

Common categories: Groceries, Food Delivery, Dining Out, Transport, Fuel, Shopping, Entertainment, Utilities, Rent, Insurance, Healthcare, Education, Travel, Subscriptions, EMI, Investment, Salary, Transfer, Other.

Rules:
- Remove transaction IDs, reference numbers, dates from the merchant name
- Capitalize properly (title case)
- If the merchant is a well-known brand, use the standard name
- If you cannot determine the category, set it to null
- Return ONLY valid JSON"""


async def llm_normalize_merchant(
    client: LLMClient, raw_description: str
) -> tuple[str, str | None]:
    """Ask LLM to clean up a raw merchant name and suggest a category.

    Returns (normalized_name, suggested_category_name).
    Falls back to (raw_description, None) on error.
    """
    sanitized = sanitize_for_llm(raw_description)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Clean up this merchant: {sanitized}"},
    ]

    response_text = await client.chat(messages, max_tokens=800, temperature=0.1)
    if not response_text:
        return raw_description, None

    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        data = json.loads(cleaned)
        merchant_name = str(data.get("merchant_name", raw_description)).strip()
        category = data.get("category")
        if category:
            category = str(category).strip()
            if category.lower() == "null":
                category = None

        return merchant_name or raw_description, category

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Could not parse LLM merchant response: %s — %s", exc, response_text[:200])
        return raw_description, None
