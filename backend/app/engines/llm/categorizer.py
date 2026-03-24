"""LLM categorizer — picks the best spending category for a transaction."""

from __future__ import annotations

import logging

from app.engines.llm.client import LLMClient
from app.engines.llm.sanitizer import sanitize_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial transaction categorizer. Given a transaction description, amount, and a list of available categories, pick the single best matching category.

Rules:
- Reply with ONLY the category name, nothing else
- The category must be exactly one from the provided list
- If none match well, reply with "None"
- Do NOT add explanation or punctuation"""


async def llm_categorize_transaction(
    client: LLMClient,
    description: str,
    amount: float,
    categories: list[str],
) -> str | None:
    """Ask LLM to pick the best category from the given list.

    Returns category name (str) or None if the LLM cannot determine one.
    """
    if not categories:
        return None

    sanitized = sanitize_for_llm(description)
    categories_str = ", ".join(categories)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Transaction: {sanitized}\n"
                f"Amount: {amount}\n"
                f"Categories: {categories_str}\n\n"
                "Which category?"
            ),
        },
    ]

    response_text = await client.chat(messages, max_tokens=500, temperature=0.1)
    if not response_text:
        return None

    result = response_text.strip().strip('"').strip("'").strip(".")
    if result.lower() in ("none", "null", "n/a", "unknown", ""):
        return None

    # Fuzzy match against the provided categories (case-insensitive)
    result_lower = result.lower()
    for cat in categories:
        if cat.lower() == result_lower:
            return cat

    # Try partial match
    for cat in categories:
        if result_lower in cat.lower() or cat.lower() in result_lower:
            return cat

    logger.warning(
        "LLM returned category '%s' which doesn't match any of %s",
        result,
        categories,
    )
    return None
