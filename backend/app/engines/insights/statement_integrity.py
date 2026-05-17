"""Credit-card statement integrity checks (deterministic + optional LLM review)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.llm.sanitizer import sanitize_for_llm
from app.models.parsed_transaction import ParsedTransaction
from app.models.statement import Statement


@dataclass
class StatementIntegrityEvaluation:
    status: str
    debit_total: float
    credit_total: float
    net_activity: float
    total_amount_due: float | None
    min_amount_due: float | None
    previous_balance: float | None
    closing_balance: float | None
    expected_closing_balance: float | None
    due_gap: float | None
    closing_balance_gap: float | None
    tolerance_due: float
    tolerance_balance: float
    notes: list[str]


def evaluate_credit_card_integrity(
    *,
    debit_total: float,
    credit_total: float,
    total_amount_due: float | None,
    min_amount_due: float | None,
    previous_balance: float | None,
    closing_balance: float | None,
    transaction_count: int,
) -> StatementIntegrityEvaluation:
    debit_total = round(float(debit_total), 2)
    credit_total = round(float(credit_total), 2)
    net_activity = round(debit_total - credit_total, 2)

    due = float(total_amount_due) if total_amount_due is not None else None
    min_due = float(min_amount_due) if min_amount_due is not None else None
    prev = float(previous_balance) if previous_balance is not None else None
    close = float(closing_balance) if closing_balance is not None else None

    tolerance_due = round(max(500.0, abs(due or 0.0) * 0.10), 2)
    tolerance_balance = round(max(250.0, abs(close or 0.0) * 0.02), 2)

    due_gap = round(abs(due - net_activity), 2) if due is not None else None
    expected_closing = round(prev + net_activity, 2) if prev is not None else None
    closing_gap = (
        round(abs(close - expected_closing), 2)
        if close is not None and expected_closing is not None
        else None
    )

    notes: list[str] = []
    aligns_due = due_gap is not None and due_gap <= tolerance_due
    aligns_balance = closing_gap is not None and closing_gap <= tolerance_balance

    if transaction_count == 0:
        notes.append("No parsed transactions were found in this statement.")
    if due is None:
        notes.append("Statement total due is missing; due-amount cross-check skipped.")
    elif prev is not None:
        expected_due = round(prev + net_activity, 2)
        due_gap_v2 = round(abs(due - expected_due), 2)
        aligns_due_v2 = due_gap_v2 <= tolerance_due
        if aligns_due_v2:
            notes.append("Net activity vs total due (with previous balance) is consistent within tolerance.")
        else:
            notes.append(f"Net activity vs total due (with previous balance) mismatch is INR {due_gap_v2:,.2f}.")
    else:
        aligns_due_v2 = False
        due_gap_v2 = None
    if aligns_due:
        notes.append("Net activity is consistent with total due within tolerance.")
    elif due_gap is not None and prev is None:
        notes.append(f"Net activity vs total due mismatch is INR {due_gap:,.2f}.")

    if close is None or prev is None:
        notes.append(
            "Opening/closing balance fields are incomplete; "
            "balance-walk check is partial."
        )
    if aligns_balance:
        notes.append("Balance-walk check is consistent within tolerance.")
    elif closing_gap is not None:
        notes.append(f"Balance-walk mismatch is INR {closing_gap:,.2f}.")

    if prev is not None and aligns_due_v2:
        status = "ok" if transaction_count > 0 else "review"
    elif transaction_count > 0 and (aligns_due or aligns_balance):
        status = "ok"
    else:
        status = "review"
    return StatementIntegrityEvaluation(
        status=status,
        debit_total=debit_total,
        credit_total=credit_total,
        net_activity=net_activity,
        total_amount_due=due,
        min_amount_due=min_due,
        previous_balance=prev,
        closing_balance=close,
        expected_closing_balance=expected_closing,
        due_gap=due_gap,
        closing_balance_gap=closing_gap,
        tolerance_due=tolerance_due,
        tolerance_balance=tolerance_balance,
        notes=notes,
    )


async def build_credit_card_statement_integrity(
    db: AsyncSession,
    user_id: uuid.UUID,
    statement: Statement,
) -> dict:
    txns = (
        await db.execute(
            select(
                ParsedTransaction.amount,
                ParsedTransaction.direction,
                ParsedTransaction.description_raw,
            )
            .where(ParsedTransaction.user_id == user_id)
            .where(ParsedTransaction.statement_id == statement.id)
            .where(ParsedTransaction.is_quarantined == False)  # noqa: E712
        )
    ).all()

    debit_total = sum(float(amount) for amount, direction, _ in txns if direction == "debit")
    credit_total = sum(float(amount) for amount, direction, _ in txns if direction == "credit")
    eval_result = evaluate_credit_card_integrity(
        debit_total=debit_total,
        credit_total=credit_total,
        total_amount_due=float(statement.total_amount_due) if statement.total_amount_due else None,
        min_amount_due=float(statement.min_amount_due) if statement.min_amount_due else None,
        previous_balance=float(statement.previous_balance) if statement.previous_balance else None,
        closing_balance=float(statement.closing_balance) if statement.closing_balance else None,
        transaction_count=len(txns),
    )

    llm_status = None
    llm_confidence = None
    llm_reason = None
    if settings.llm_enabled:
        llm_status, llm_confidence, llm_reason = await _llm_integrity_review(
            statement,
            txns,
            eval_result,
        )

    final_status = eval_result.status
    if llm_status == "review":
        final_status = "review"

    return {
        "statement_id": str(statement.id),
        "account_type": statement.account_type,
        "status": final_status,
        "transaction_count": len(txns),
        "debit_total": eval_result.debit_total,
        "credit_total": eval_result.credit_total,
        "net_activity": eval_result.net_activity,
        "total_amount_due": eval_result.total_amount_due,
        "min_amount_due": eval_result.min_amount_due,
        "previous_balance": eval_result.previous_balance,
        "closing_balance": eval_result.closing_balance,
        "expected_closing_balance": eval_result.expected_closing_balance,
        "due_gap": eval_result.due_gap,
        "closing_balance_gap": eval_result.closing_balance_gap,
        "tolerance_due": eval_result.tolerance_due,
        "tolerance_balance": eval_result.tolerance_balance,
        "llm_status": llm_status,
        "llm_confidence": llm_confidence,
        "llm_reason": llm_reason,
        "notes": eval_result.notes,
    }


async def _llm_integrity_review(
    statement: Statement,
    txns: list,
    eval_result: StatementIntegrityEvaluation,
) -> tuple[str | None, float | None, str | None]:
    try:
        from app.engines.llm.factory import build_client_for_task

        client, _ = build_client_for_task(task="integrity_review")
        top_samples = [sanitize_for_llm(row[2]) for row in txns[:8]]
        prompt = (
            "Review credit-card statement extraction integrity.\n"
            f"Bank: {statement.bank_name}\n"
            f"Debit total: {eval_result.debit_total}\n"
            f"Credit total: {eval_result.credit_total}\n"
            f"Net activity: {eval_result.net_activity}\n"
            f"Total due: {eval_result.total_amount_due}\n"
            f"Min due: {eval_result.min_amount_due}\n"
            f"Previous balance: {eval_result.previous_balance}\n"
            f"Closing balance: {eval_result.closing_balance}\n"
            f"Expected closing balance: {eval_result.expected_closing_balance}\n"
            f"Due gap: {eval_result.due_gap}\n"
            f"Closing gap: {eval_result.closing_balance_gap}\n"
            f"Samples: {top_samples}\n"
        )
        payload = await client.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON: "
                        '{"status":"ok|review","confidence":0..1,"reason":"<=25 words"}'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "confidence": {"type": ["number", "null"]},
                    "reason": {"type": ["string", "null"]},
                },
                "required": ["status"],
                "additionalProperties": False,
            },
            max_tokens=180,
            temperature=0.0,
        )
        if not payload:
            return None, None, None
        status = str(payload.get("status", "")).strip().lower()
        if status not in {"ok", "review"}:
            status = None
        confidence = payload.get("confidence")
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except Exception:
            confidence = None
        reason = str(payload.get("reason", "")).strip()[:220] or None
        return status, confidence, reason
    except Exception:
        return None, None, None
