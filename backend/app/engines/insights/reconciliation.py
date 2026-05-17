from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.models.transaction_source import TransactionSource


@dataclass
class TransferCandidate:
    id: uuid.UUID
    transaction_date: date
    amount: float
    direction: str
    transaction_nature: str
    merchant_raw: str
    bank_name: str | None
    account_type: str | None
    account_masked: str | None
    source_files: list[str]


def pair_transfer_candidates(
    candidates: list[TransferCandidate],
    max_gap_days: int = 5,
) -> tuple[list[dict], list[TransferCandidate]]:
    debits = sorted(
        [c for c in candidates if c.direction == "debit"],
        key=lambda c: (c.transaction_date, c.id),
    )
    credits = sorted(
        [c for c in candidates if c.direction == "credit"],
        key=lambda c: (c.transaction_date, c.id),
    )

    matched_credit_ids: set[uuid.UUID] = set()
    matched_debit_ids: set[uuid.UUID] = set()
    pairs: list[dict] = []

    for debit in debits:
        best_credit: TransferCandidate | None = None
        best_score: float | None = None
        best_gap = 0
        for credit in credits:
            if credit.id in matched_credit_ids:
                continue
            if not _amount_equal(debit.amount, credit.amount):
                continue
            gap = abs((debit.transaction_date - credit.transaction_date).days)
            if gap > max_gap_days:
                continue

            # Lower score is better: prefer closest date + different accounts.
            score = float(gap)
            if debit.bank_name and credit.bank_name and debit.bank_name == credit.bank_name:
                score += 1.5
            if (
                debit.account_masked
                and credit.account_masked
                and debit.account_masked == credit.account_masked
            ):
                score += 2.0
            if debit.account_type and credit.account_type and debit.account_type == credit.account_type:
                score += 1.0

            if best_score is None or score < best_score:
                best_score = score
                best_credit = credit
                best_gap = gap

        if best_credit is None:
            continue

        matched_debit_ids.add(debit.id)
        matched_credit_ids.add(best_credit.id)
        confidence = _confidence_for_pair(debit, best_credit, best_gap)
        pairs.append(
            {
                "amount": round(float(debit.amount), 2),
                "day_gap": best_gap,
                "confidence": confidence,
                "reasoning": _reasoning_for_pair(debit, best_credit, best_gap),
                "debit": _candidate_to_dict(debit),
                "credit": _candidate_to_dict(best_credit),
            }
        )

    unmatched = [
        c for c in candidates if c.id not in matched_debit_ids and c.id not in matched_credit_ids
    ]
    pairs.sort(key=lambda p: (p["day_gap"], -p["amount"]))
    return pairs, unmatched


async def build_transfer_reconciliation(
    db: AsyncSession,
    user_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    max_gap_days: int = 5,
    limit: int = 300,
) -> dict:
    query = (
        select(CanonicalTransaction)
        .where(CanonicalTransaction.user_id == user_id)
        .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
        .where(CanonicalTransaction.transaction_nature == "transfer_internal")
        .order_by(CanonicalTransaction.transaction_date.desc(), CanonicalTransaction.created_at.desc())
        .limit(limit)
    )
    if date_from:
        query = query.where(CanonicalTransaction.transaction_date >= date_from)
    if date_to:
        query = query.where(CanonicalTransaction.transaction_date <= date_to)

    txns = (await db.execute(query)).scalars().all()
    if not txns:
        return {
            "total_transfer_transactions": 0,
            "matched_pairs": 0,
            "unmatched_transactions": 0,
            "matched_amount": 0.0,
            "match_rate": 0.0,
            "pairs": [],
            "unmatched": [],
        }

    source_map = await _load_source_files(db, [t.id for t in txns])
    candidates = [
        TransferCandidate(
            id=t.id,
            transaction_date=t.transaction_date,
            amount=float(t.amount),
            direction=t.direction,
            transaction_nature=t.transaction_nature,
            merchant_raw=t.merchant_raw,
            bank_name=t.bank_name,
            account_type=t.account_type,
            account_masked=t.account_masked,
            source_files=sorted(source_map.get(t.id, set())),
        )
        for t in sorted(txns, key=lambda x: (x.transaction_date, x.created_at))
    ]

    pairs, unmatched = pair_transfer_candidates(candidates, max_gap_days=max_gap_days)
    matched_amount = round(sum(float(p["amount"]) for p in pairs), 2)
    total = len(candidates)
    matched_txn_count = len(pairs) * 2
    match_rate = round((matched_txn_count / total) if total else 0.0, 4)

    return {
        "total_transfer_transactions": total,
        "matched_pairs": len(pairs),
        "unmatched_transactions": len(unmatched),
        "matched_amount": matched_amount,
        "match_rate": match_rate,
        "pairs": pairs,
        "unmatched": [_candidate_to_dict(c) for c in unmatched],
    }


async def _load_source_files(
    db: AsyncSession, canonical_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[str]]:
    if not canonical_ids:
        return {}

    query = (
        select(TransactionSource.canonical_txn_id, RawPdf.original_filename)
        .join(ParsedTransaction, ParsedTransaction.id == TransactionSource.parsed_txn_id)
        .join(Statement, Statement.id == ParsedTransaction.statement_id, isouter=True)
        .join(RawPdf, RawPdf.id == Statement.pdf_id, isouter=True)
        .where(TransactionSource.canonical_txn_id.in_(canonical_ids))
    )
    rows = (await db.execute(query)).all()

    out: dict[uuid.UUID, set[str]] = {}
    for canonical_txn_id, filename in rows:
        if not filename:
            continue
        out.setdefault(canonical_txn_id, set()).add(filename)
    return out


def _amount_equal(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= 0.50


def _confidence_for_pair(debit: TransferCandidate, credit: TransferCandidate, gap_days: int) -> float:
    confidence = Decimal("0.92") - Decimal(gap_days) * Decimal("0.08")
    if debit.bank_name and credit.bank_name and debit.bank_name == credit.bank_name:
        confidence -= Decimal("0.10")
    if debit.account_type and credit.account_type and debit.account_type == credit.account_type:
        confidence -= Decimal("0.05")
    if (
        debit.account_masked
        and credit.account_masked
        and debit.account_masked == credit.account_masked
    ):
        confidence -= Decimal("0.15")

    if confidence < Decimal("0.30"):
        confidence = Decimal("0.30")
    if confidence > Decimal("0.99"):
        confidence = Decimal("0.99")
    return float(round(confidence, 2))


def _reasoning_for_pair(debit: TransferCandidate, credit: TransferCandidate, gap_days: int) -> str:
    parts = [f"same amount, {gap_days} day gap"]
    if debit.bank_name and credit.bank_name and debit.bank_name != credit.bank_name:
        parts.append("cross-bank movement")
    if debit.account_type and credit.account_type and debit.account_type != credit.account_type:
        parts.append("cross-account-type movement")
    if debit.source_files and credit.source_files:
        parts.append("backed by statement sources")
    return "; ".join(parts)


def _candidate_to_dict(c: TransferCandidate) -> dict:
    return {
        "id": str(c.id),
        "transaction_date": c.transaction_date,
        "amount": round(float(c.amount), 2),
        "direction": c.direction,
        "transaction_nature": c.transaction_nature,
        "merchant_raw": c.merchant_raw,
        "bank_name": c.bank_name,
        "account_type": c.account_type,
        "account_masked": c.account_masked,
        "source_files": c.source_files,
    }
