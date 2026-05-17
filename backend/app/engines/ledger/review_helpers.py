from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.review_task import ReviewTask


def _stringify(value: Any) -> str:
    return str(value) if value is not None else ""


async def create_review_task_for_canonical(
    db: AsyncSession,
    *,
    parsed: ParsedTransaction | None,
    canonical: CanonicalTransaction,
    reasons: list[str],
    statement_id: uuid.UUID | None = None,
    raw_evidence: dict[str, Any] | None = None,
    title: str = "Transaction needs review",
) -> ReviewTask:
    """Create a review task linked to a canonical transaction.

    `statement_id` is optional so SMS/manual sources can use the same audit path
    as statement extraction without fabricating a Statement row.
    """
    normalized_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    payload: dict[str, Any] = {
        "canonical_transaction_id": str(canonical.id),
        "reasons": normalized_reasons,
        "raw_evidence": raw_evidence or canonical.source_evidence or {},
    }
    if parsed is not None:
        payload.update(
            {
                "parsed_transaction_id": str(parsed.id),
                "source_type": parsed.source_type,
                "source_id": str(parsed.source_id),
            }
        )

    task = ReviewTask(
        user_id=canonical.user_id,
        statement_id=statement_id,
        task_type="transaction_review",
        status="open",
        reason_code=(normalized_reasons[0] if normalized_reasons else "needs_review")[:60],
        title=title,
        details=", ".join(normalized_reasons) or None,
        payload_json={key: _json_safe(value) for key, value in payload.items()},
    )
    db.add(task)
    await db.flush()
    canonical.review_task_id = task.id
    return task


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _stringify(value)
