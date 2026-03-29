"""LLM fallback parser — extracts transactions from unrecognized bank statements via LLM."""

from __future__ import annotations

import json
import logging
from datetime import date

from app.engines.llm.client import LLMClient
from app.engines.llm.knowledge import StatementKnowledgeContext
from app.engines.llm.sanitizer import sanitize_for_llm
from app.engines.parser.hints import normalize_bank_hint
from app.engines.parser.base import ExtractedStatement, ExtractedTransaction

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial document parser. Extract transaction data from the bank statement text provided.

Return a JSON object with these fields:
{
  "bank_name": "string — name of the bank",
  "account_type": "credit_card | savings | current",
  "account_number_masked": "string or null — last 4 digits like XX1234",
  "statement_period_start": "YYYY-MM-DD or null",
  "statement_period_end": "YYYY-MM-DD or null",
  "opening_balance": number or null,
  "closing_balance": number or null,
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "string",
      "amount": number (positive),
      "direction": "debit | credit",
      "reference_number": "string or null"
    }
  ]
}

Rules:
- All amounts must be positive numbers. Use "direction" to indicate debit/credit.
- Parse dates carefully — they may be in DD/MM/YYYY, DD-MM-YYYY, DD MMM YYYY, etc.
- If a transaction has no date, use the previous transaction's date.
- Use the current document text as the primary source of truth. Customer history is supportive context only.
- For credit-card statements, include statement-level metadata such as total due, minimum due, previous balance, and payments received when visible.
- Return ONLY valid JSON, no explanations or markdown."""


async def llm_parse_statement(
    client: LLMClient,
    page_text: str,
    *,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    knowledge_context: StatementKnowledgeContext | None = None,
) -> ExtractedStatement | None:
    """Use LLM to extract transactions from bank statement text.

    Used when no template parser matches the PDF.
    Returns ExtractedStatement or None on failure.
    """
    sanitized = sanitize_for_llm(page_text)

    # Truncate very long statements to stay within context window
    if len(sanitized) > 12000:
        sanitized = sanitized[:12000] + "\n... [TRUNCATED]"

    context_text = knowledge_context.as_prompt_context() if knowledge_context else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"User-provided bank hint: {bank_hint or 'none'}\n"
                f"User-provided account type hint: {account_type_hint or 'none'}\n"
                f"Relevant customer context:\n{context_text or 'none'}\n\n"
                f"Extract transactions from this statement:\n\n{sanitized}"
            ),
        },
    ]

    response_text = await client.chat(
        messages,
        max_tokens=2000,
        temperature=0.1,
        timeout_sec=35.0,
        max_attempts=1,
    )
    if not response_text:
        logger.warning("LLM returned empty response for statement parsing")
        return None

    try:
        # Strip markdown fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("LLM response was not valid JSON: %s — %s", exc, response_text[:200])
        return None

    # Validate and build ExtractedStatement
    try:
        transactions: list[ExtractedTransaction] = []
        for i, txn in enumerate(data.get("transactions", [])):
            txn_date = _parse_date(txn.get("date", ""))
            if txn_date is None:
                logger.warning("Skipping transaction %d: invalid date '%s'", i, txn.get("date"))
                continue

            amount = float(txn.get("amount", 0))
            if amount <= 0:
                continue

            direction = txn.get("direction", "debit").lower()
            if direction not in ("debit", "credit"):
                direction = "debit"

            transactions.append(
                ExtractedTransaction(
                    transaction_date=txn_date,
                    posting_date=None,
                    description=str(txn.get("description", "")).strip(),
                    amount=amount,
                    direction=direction,
                    reference_number=txn.get("reference_number"),
                    confidence=0.7,  # Lower confidence for LLM-parsed
                )
            )

        if not transactions:
            logger.warning("LLM parsed zero valid transactions")
            return None

        bank_name = normalize_bank_hint(data.get("bank_name")) or bank_hint or "Unknown"
        account_type = str(data.get("account_type", "savings")).strip().lower()
        if account_type_hint == "credit_card":
            account_type = "credit_card"
        elif account_type_hint == "bank_account" and account_type == "credit_card":
            account_type = "savings"
        elif account_type not in {"credit_card", "savings", "current"}:
            account_type = "savings"

        result = ExtractedStatement(
            bank_name=bank_name,
            account_type=account_type,
            account_number_masked=data.get("account_number_masked"),
            statement_period_start=_parse_date(data.get("statement_period_start")),
            statement_period_end=_parse_date(data.get("statement_period_end")),
            due_date=_parse_date(data.get("due_date")),
            min_amount_due=_safe_float(data.get("min_amount_due")),
            total_amount_due=_safe_float(data.get("total_amount_due")),
            previous_balance=_safe_float(data.get("previous_balance")),
            payments_received=_safe_float(data.get("payments_received")),
            opening_balance=_safe_float(data.get("opening_balance")),
            closing_balance=_safe_float(data.get("closing_balance")),
            transactions=transactions,
            parser_id="llm_fallback",
            warnings=["Parsed by LLM fallback — review recommended"],
        )
        return result

    except Exception as exc:
        logger.error("Error building ExtractedStatement from LLM response: %s", exc)
        return None


def _parse_date(val: str | None) -> date | None:
    """Try to parse a date string in common formats."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return date.fromisoformat(val) if fmt == "%Y-%m-%d" else __import__("datetime").datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _safe_float(val: object) -> float | None:
    """Safely convert a value to float or return None."""
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
