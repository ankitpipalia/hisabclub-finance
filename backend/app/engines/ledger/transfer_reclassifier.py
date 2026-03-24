"""Shared transfer/card-payment reclassification pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.insights.reconciliation import TransferCandidate, pair_transfer_candidates
from app.engines.ledger.nature import infer_transaction_nature
from app.engines.llm.client import LLMClient
from app.engines.llm.transfer_classifier import llm_is_credit_card_payment
from app.models.canonical_transaction import CanonicalTransaction

_TRANSFERISH_HINTS = (
    "TRANSFER",
    "TELE TRANSFER",
    "CREDIT CARD PAYMENT",
    "CC PAYMENT",
    "CARD PAYMENT",
    "BILLDESK",
    "IMPS",
    "NEFT",
    "RTGS",
    "UPI",
    "AUTOPAY",
)


@dataclass
class TransferReclassifyResult:
    scanned: int
    updated: int
    matched_credit_card_pairs: int
    llm_checked: int
    llm_promoted: int


def _looks_transferish(text: str) -> bool:
    upper = (text or "").upper()
    return any(token in upper for token in _TRANSFERISH_HINTS)


def _append_note(existing: str | None, message: str) -> str:
    if not existing:
        return message
    if message in existing:
        return existing
    return f"{existing}\n{message}"


async def reclassify_transfer_payments_for_user(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 365,
    limit: int = 3000,
    max_gap_days: int = 7,
    use_llm: bool = True,
) -> TransferReclassifyResult:
    from_date = date.today() - timedelta(days=days)
    txns = (
        await db.execute(
            select(CanonicalTransaction)
            .where(CanonicalTransaction.user_id == user_id)
            .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
            .where(CanonicalTransaction.transaction_date >= from_date)
            .order_by(
                CanonicalTransaction.transaction_date.desc(),
                CanonicalTransaction.created_at.desc(),
            )
            .limit(limit)
        )
    ).scalars().all()

    if not txns:
        return TransferReclassifyResult(
            scanned=0,
            updated=0,
            matched_credit_card_pairs=0,
            llm_checked=0,
            llm_promoted=0,
        )

    by_id = {str(txn.id): txn for txn in txns}
    updated_ids: set[uuid.UUID] = set()

    # Pass 1: deterministic natures from description/account context.
    for txn in txns:
        inferred = infer_transaction_nature(
            description_raw=txn.merchant_raw,
            direction=txn.direction,
            account_type=txn.account_type,
        )
        if inferred != txn.transaction_nature:
            txn.transaction_nature = inferred
            updated_ids.add(txn.id)

    # Pass 2: amount/date pairing for transfer-like rows.
    candidate_rows = [
        txn
        for txn in txns
        if txn.transaction_nature == "transfer_internal" or _looks_transferish(txn.merchant_raw)
    ]
    candidates = [
        TransferCandidate(
            id=txn.id,
            transaction_date=txn.transaction_date,
            amount=float(txn.amount),
            direction=txn.direction,
            transaction_nature=txn.transaction_nature,
            merchant_raw=txn.merchant_raw,
            bank_name=txn.bank_name,
            account_type=txn.account_type,
            account_masked=txn.account_masked,
            source_files=[],
        )
        for txn in candidate_rows
    ]
    pairs, _ = pair_transfer_candidates(candidates, max_gap_days=max_gap_days)

    matched_credit_card_pairs = 0
    for pair in pairs:
        debit_txn = by_id.get(pair["debit"]["id"])
        credit_txn = by_id.get(pair["credit"]["id"])
        if debit_txn is None or credit_txn is None:
            continue

        account_types = {
            (debit_txn.account_type or "").lower(),
            (credit_txn.account_type or "").lower(),
        }
        if "credit_card" not in account_types:
            continue
        if not ({"savings", "current", "salary"} & account_types):
            continue

        matched_credit_card_pairs += 1
        for txn in (debit_txn, credit_txn):
            if txn.transaction_nature != "transfer_internal":
                txn.transaction_nature = "transfer_internal"
                updated_ids.add(txn.id)
            txn.notes = _append_note(
                txn.notes,
                "Auto-matched with opposite leg as credit-card bill payment.",
            )

    # Pass 3: ambiguous transfer-like rows via local LLM.
    llm_checked = 0
    llm_promoted = 0
    if use_llm and settings.llm_enabled:
        try:
            client = LLMClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
            )
            for txn in txns:
                if txn.transaction_nature == "transfer_internal":
                    continue
                if not _looks_transferish(txn.merchant_raw):
                    continue

                llm_checked += 1
                decision = await llm_is_credit_card_payment(
                    client=client,
                    description=txn.merchant_raw,
                    direction=txn.direction,
                    account_type=txn.account_type,
                    bank_name=txn.bank_name,
                    amount=float(txn.amount),
                )
                if not decision:
                    continue
                if not decision["is_credit_card_payment"] or decision["confidence"] < 0.6:
                    continue

                txn.transaction_nature = "transfer_internal"
                txn.notes = _append_note(
                    txn.notes,
                    f"LLM reclassified as card payment/internal transfer ({decision['reason']}).",
                )
                updated_ids.add(txn.id)
                llm_promoted += 1
        except Exception:
            # Non-blocking; deterministic passes are still applied.
            pass

    return TransferReclassifyResult(
        scanned=len(txns),
        updated=len(updated_ids),
        matched_credit_card_pairs=matched_credit_card_pairs,
        llm_checked=llm_checked,
        llm_promoted=llm_promoted,
    )
