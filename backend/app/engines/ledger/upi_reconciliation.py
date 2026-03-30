"""Reconcile failed UPI debit transactions with corresponding credit reversals."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.transfer_match import TransferMatch

_UPI_KEYWORDS = ("UPI", "VPA", "PAYTM", "PHONEPE", "GPAY", "BHIM")
_REVERSAL_KEYWORDS = ("REVERSAL", "REV", "REFUND", "FAILED", "FAILURE", "REVERSED")


@dataclass
class UpiReconcileResult:
    scanned: int
    matched_pairs: int
    updated_transactions: int


def _is_upi(text: str | None) -> bool:
    upper = (text or "").upper()
    return any(token in upper for token in _UPI_KEYWORDS)


def _is_reversal(text: str | None) -> bool:
    upper = (text or "").upper()
    return any(token in upper for token in _REVERSAL_KEYWORDS)


def _append_note(existing: str | None, message: str) -> str:
    if not existing:
        return message
    if message in existing:
        return existing
    return f"{existing}\n{message}"


async def reconcile_upi_failures_for_user(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 365,
    max_gap_days: int = 3,
    limit: int = 5000,
) -> UpiReconcileResult:
    from_date = date.today() - timedelta(days=days)
    rows = (
        await db.execute(
            select(CanonicalTransaction)
            .where(CanonicalTransaction.user_id == user_id)
            .where(CanonicalTransaction.transaction_date >= from_date)
            .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
            .order_by(CanonicalTransaction.transaction_date.desc())
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return UpiReconcileResult(scanned=0, matched_pairs=0, updated_transactions=0)

    debit_candidates = [
        txn
        for txn in rows
        if txn.direction == "debit"
        and _is_upi(txn.merchant_raw)
        and not _is_reversal(txn.merchant_raw)
    ]
    credit_candidates = [
        txn
        for txn in rows
        if txn.direction == "credit" and _is_upi(txn.merchant_raw) and _is_reversal(txn.merchant_raw)
    ]

    used_credit_ids: set[uuid.UUID] = set()
    matched_pairs = 0
    updated_ids: set[uuid.UUID] = set()
    for debit in debit_candidates:
        best_credit: CanonicalTransaction | None = None
        best_gap = 999
        for credit in credit_candidates:
            if credit.id in used_credit_ids:
                continue
            if abs(float(credit.amount) - float(debit.amount)) > 0.01:
                continue
            gap = abs((credit.transaction_date - debit.transaction_date).days)
            if gap > max_gap_days:
                continue
            if gap < best_gap:
                best_gap = gap
                best_credit = credit

        if best_credit is None:
            continue
        used_credit_ids.add(best_credit.id)
        matched_pairs += 1

        for txn in (debit, best_credit):
            txn.transaction_nature = "transfer_internal"
            txn.notes = _append_note(
                txn.notes,
                "UPI failed debit/credit reversal pair reconciled automatically.",
            )
            updated_ids.add(txn.id)

        existing = (
            await db.execute(
                select(TransferMatch)
                .where(
                    TransferMatch.user_id == user_id,
                    TransferMatch.debit_canonical_id == debit.id,
                    TransferMatch.credit_canonical_id == best_credit.id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                TransferMatch(
                    user_id=user_id,
                    debit_canonical_id=debit.id,
                    credit_canonical_id=best_credit.id,
                    match_type="upi_failure_reversal",
                    confidence=0.88,
                    resolution_status="auto",
                )
            )
        else:
            existing.match_type = "upi_failure_reversal"
            existing.confidence = 0.88
            if existing.resolution_status not in {"accepted", "rejected"}:
                existing.resolution_status = "auto"

    return UpiReconcileResult(
        scanned=len(rows),
        matched_pairs=matched_pairs,
        updated_transactions=len(updated_ids),
    )

