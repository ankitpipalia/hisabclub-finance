"""Local-LLM transaction correction chat workflow."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.llm.sanitizer import sanitize_for_llm
from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.user_override import UserOverride

_SUPPORTED_ACTIONS = {
    "set_category",
    "set_nature",
    "set_notes",
    "exclude_transaction",
    "include_transaction",
}

_ALLOWED_NATURES = {
    "expense",
    "income",
    "transfer_internal",
    "refund",
    "investment",
    "tax",
    "interest_income",
    "dividend_income",
}


@dataclass
class CorrectionChatResult:
    reply: str
    proposed_count: int
    applied_count: int
    skipped_count: int
    warnings: list[str]
    actions: list[dict]


async def run_transaction_correction_chat(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    apply_changes: bool,
    max_candidates: int,
) -> CorrectionChatResult:
    if not settings.llm_enabled:
        raise ValueError("Local LLM is disabled. Enable LLM_ENABLED=true to use correction chat.")

    categories = (
        await db.execute(
            select(Category)
            .where((Category.user_id == user_id) | (Category.user_id.is_(None)))
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
    ).scalars().all()
    category_by_name = {c.name.strip().lower(): c for c in categories if c.name}
    category_names = [c.name for c in categories if c.name]

    rows = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(CanonicalTransaction.user_id == user_id)
            .order_by(
                CanonicalTransaction.transaction_date.desc(),
                CanonicalTransaction.created_at.desc(),
            )
            .limit(max_candidates)
        )
    ).all()
    if not rows:
        return CorrectionChatResult(
            reply="No transactions are available for correction yet.",
            proposed_count=0,
            applied_count=0,
            skipped_count=0,
            warnings=[],
            actions=[],
        )

    txn_by_id: dict[str, CanonicalTransaction] = {}
    candidates: list[dict] = []
    for txn, category_name in rows:
        txn_id = str(txn.id)
        txn_by_id[txn_id] = txn
        candidates.append(
            {
                "transaction_id": txn_id,
                "date": txn.transaction_date.isoformat(),
                "amount": float(txn.amount),
                "direction": txn.direction,
                "nature": txn.transaction_nature,
                "category_name": category_name,
                "bank_name": txn.bank_name,
                "account_type": txn.account_type,
                "description": sanitize_for_llm(txn.merchant_raw),
                "notes": sanitize_for_llm(txn.notes or ""),
            }
        )

    schema = {
        "type": "object",
        "required": ["reply", "actions", "needs_user_clarification", "clarification_question"],
        "properties": {
            "reply": {"type": "string"},
            "needs_user_clarification": {"type": "boolean"},
            "clarification_question": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["action", "transaction_id", "reason"],
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": sorted(_SUPPORTED_ACTIONS),
                        },
                        "transaction_id": {"type": "string"},
                        "category_name": {"type": "string"},
                        "transaction_nature": {"type": "string"},
                        "notes": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "maxItems": 40,
            },
        },
        "additionalProperties": False,
    }

    prompt_payload = {
        "user_request": message,
        "rules": [
            "Use only provided transaction_id values.",
            "If instruction is ambiguous, set needs_user_clarification=true and return no actions.",
            "Do not invent transaction ids or categories.",
            "Prefer minimal edits needed to satisfy the request.",
        ],
        "supported_actions": sorted(_SUPPORTED_ACTIONS),
        "allowed_natures": sorted(_ALLOWED_NATURES),
        "available_categories": category_names,
        "transaction_candidates": candidates,
    }

    from app.engines.llm.factory import build_client_for_task

    client, _ = build_client_for_task(task="correction_chat")
    llm_payload = await client.chat_json(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a finance correction assistant. Convert user correction intent into "
                    "safe action plans over provided transaction candidates."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=True),
            },
        ],
        schema=schema,
        temperature=0.0,
        max_tokens=2400,
    )
    if not llm_payload:
        return CorrectionChatResult(
            reply="Local LLM did not return a usable correction plan. Please try again.",
            proposed_count=0,
            applied_count=0,
            skipped_count=0,
            warnings=["Empty or invalid LLM response."],
            actions=[],
        )

    reply = str(llm_payload.get("reply") or "").strip()
    needs_clarification = bool(llm_payload.get("needs_user_clarification"))
    clarification_question = str(llm_payload.get("clarification_question") or "").strip()
    raw_actions = llm_payload.get("actions")
    if not isinstance(raw_actions, list):
        raw_actions = []

    action_results: list[dict] = []
    warnings: list[str] = []
    applied_count = 0
    proposed_count = 0
    skipped_count = 0

    for idx, raw in enumerate(raw_actions):
        if not isinstance(raw, dict):
            warnings.append(f"Action {idx + 1} ignored: invalid payload.")
            continue
        action = str(raw.get("action") or "").strip()
        txn_id = str(raw.get("transaction_id") or "").strip()
        reason = str(raw.get("reason") or "").strip() or "assistant_chat"
        if action not in _SUPPORTED_ACTIONS:
            warnings.append(f"Action {idx + 1} ignored: unsupported action '{action}'.")
            continue
        txn = txn_by_id.get(txn_id)
        if txn is None:
            warnings.append(f"Action {idx + 1} ignored: unknown transaction id '{txn_id}'.")
            continue

        planned = _plan_action(
            action=action,
            raw=raw,
            txn=txn,
            category_by_name=category_by_name,
        )
        if planned is None:
            skipped_count += 1
            action_results.append(
                {
                    "action": action,
                    "transaction_id": txn_id,
                    "status": "skipped",
                    "detail": "Missing or invalid action fields.",
                }
            )
            continue
        proposed_count += 1
        if not apply_changes:
            action_results.append(
                {
                    "action": action,
                    "transaction_id": txn_id,
                    "status": "proposed",
                    "detail": planned["detail"],
                    "before": planned.get("before"),
                    "after": planned.get("after"),
                }
            )
            continue

        changed = _apply_planned_action(
            db=db,
            user_id=user_id,
            txn=txn,
            planned=planned,
            reason=reason,
        )
        if changed:
            applied_count += 1
            status = "applied"
        else:
            skipped_count += 1
            status = "skipped"
        action_results.append(
            {
                "action": action,
                "transaction_id": txn_id,
                "status": status,
                "detail": planned["detail"],
                "before": planned.get("before"),
                "after": planned.get("after"),
            }
        )

    if needs_clarification and clarification_question:
        warnings.append(clarification_question)
    if not reply:
        reply = (
            "I prepared correction actions from your prompt."
            if proposed_count
            else "No concrete correction actions were identified."
        )

    return CorrectionChatResult(
        reply=reply,
        proposed_count=proposed_count,
        applied_count=applied_count,
        skipped_count=skipped_count,
        warnings=warnings,
        actions=action_results,
    )


def _plan_action(
    *,
    action: str,
    raw: dict,
    txn: CanonicalTransaction,
    category_by_name: dict[str, Category],
) -> dict | None:
    txn_id = str(txn.id)
    if action == "set_category":
        category_name = str(raw.get("category_name") or "").strip()
        category = category_by_name.get(category_name.lower())
        if category is None:
            return None
        return {
            "action": action,
            "transaction_id": txn_id,
            "field": "category_id",
            "value": category.id,
            "detail": f"Set category to '{category.name}'.",
            "before": str(txn.category_id) if txn.category_id else None,
            "after": str(category.id),
        }
    if action == "set_nature":
        nature = str(raw.get("transaction_nature") or "").strip().lower()
        if nature not in _ALLOWED_NATURES:
            return None
        return {
            "action": action,
            "transaction_id": txn_id,
            "field": "transaction_nature",
            "value": nature,
            "detail": f"Set transaction nature to '{nature}'.",
            "before": txn.transaction_nature,
            "after": nature,
        }
    if action == "set_notes":
        notes = str(raw.get("notes") or "").strip()
        if not notes:
            return None
        return {
            "action": action,
            "transaction_id": txn_id,
            "field": "notes",
            "value": notes[:500],
            "detail": "Updated transaction notes.",
            "before": txn.notes,
            "after": notes[:500],
        }
    if action in {"exclude_transaction", "include_transaction"}:
        value = action == "exclude_transaction"
        return {
            "action": action,
            "transaction_id": txn_id,
            "field": "is_excluded",
            "value": value,
            "detail": (
                "Excluded transaction from analytics."
                if value
                else "Included transaction back."
            ),
            "before": str(bool(txn.is_excluded)).lower(),
            "after": str(value).lower(),
        }
    return None


def _apply_planned_action(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    txn: CanonicalTransaction,
    planned: dict,
    reason: str,
) -> bool:
    field = planned["field"]
    value = planned["value"]
    current = getattr(txn, field, None)
    if str(current) == str(value):
        return False
    db.add(
        UserOverride(
            user_id=user_id,
            canonical_txn_id=txn.id,
            field_name=field,
            old_value=_stringify(current),
            new_value=_stringify(value),
            override_reason=reason[:300],
        )
    )
    setattr(txn, field, value)
    if field == "category_id":
        txn.category_source = "user"
    return True


def _stringify(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)
