"""SMS ↔ statement matching engine (Sprint C.6).

When an SMS is promoted to `canonical_transactions` with
`extraction_source='sms'`, it represents a "pending" transaction — we have a
real-time signal from the bank/card SMS but not the durable statement
record. When a non-SMS source (template/llm/manual) later promotes a row
with the same `(account_masked, transaction_date ±3d, amount within ₹1)`,
we want to:

  1. Mark the SMS row as confirmed (extraction_source still 'sms', but a
     new `TransactionSource` link points to the statement-derived canonical).
  2. NOT create a duplicate canonical row — the existing dedup engine
     already prevents that on import.

This engine is run on-demand by `POST /api/v1/sms/match?fy=` and once
daily by the job runner.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.transaction_source import TransactionSource

logger = logging.getLogger(__name__)

_AMOUNT_TOLERANCE = Decimal("1.00")
_DATE_WINDOW_DAYS = 3


@dataclass(frozen=True)
class MatchResult:
    sms_canonical_id: uuid.UUID
    statement_canonical_id: uuid.UUID
    date_gap_days: int
    amount_gap: Decimal


@dataclass(frozen=True)
class MatchReport:
    matched_pairs: int
    sms_unmatched: int
    matches: tuple[MatchResult, ...]


def _fy_window_or_default(fy: str | None) -> tuple[date | None, date | None]:
    if not fy:
        return None, None
    from app.engines.tax.reconcile.wire import _fy_window

    try:
        return _fy_window(fy)
    except ValueError:
        return None, None


async def _candidates(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: date | None,
    end: date | None,
) -> list[CanonicalTransaction]:
    stmt = select(CanonicalTransaction).where(
        CanonicalTransaction.user_id == user_id,
        CanonicalTransaction.is_excluded == False,  # noqa: E712
    )
    if start is not None:
        stmt = stmt.where(CanonicalTransaction.transaction_date >= start)
    if end is not None:
        stmt = stmt.where(CanonicalTransaction.transaction_date <= end)
    return (await db.execute(stmt)).scalars().all()


async def _existing_source_link(
    db: AsyncSession, canonical_id: uuid.UUID
) -> bool:
    """Return True if `TransactionSource` already links these two canonicals.

    Prevents double-writing the link when the matcher is run multiple times.
    """
    row = (
        await db.execute(
            select(TransactionSource.id).where(
                TransactionSource.canonical_txn_id == canonical_id,
                TransactionSource.match_method == "sms_statement_match",
            ).limit(1)
        )
    ).first()
    return row is not None


async def match_sms_to_statements(
    db: AsyncSession,
    user_id: uuid.UUID,
    fy: str | None = None,
) -> MatchReport:
    """Pair every SMS canonical row with its statement-derived counterpart.

    Returns counts so the caller can surface them in the UI / job log.
    """
    start, end = _fy_window_or_default(fy)
    rows = await _candidates(db, user_id, start, end)

    # Bucket non-SMS rows by (account_masked, date) so per-SMS lookup is O(1).
    by_account_date: dict[tuple[str | None, date], list[CanonicalTransaction]] = defaultdict(list)
    sms_rows: list[CanonicalTransaction] = []
    for row in rows:
        if (row.extraction_source or "").lower() == "sms":
            sms_rows.append(row)
        else:
            by_account_date[(row.account_masked, row.transaction_date)].append(row)

    matches: list[MatchResult] = []
    matched_sms_ids: set[uuid.UUID] = set()

    for sms in sms_rows:
        sms_amt = Decimal(str(sms.amount))
        # Search ±N days for a non-SMS canonical with same account + amount.
        best: tuple[int, CanonicalTransaction] | None = None
        for offset in range(-_DATE_WINDOW_DAYS, _DATE_WINDOW_DAYS + 1):
            candidate_date = sms.transaction_date + timedelta(days=offset)
            for cand in by_account_date.get((sms.account_masked, candidate_date), ()):
                if cand.direction != sms.direction:
                    continue
                cand_amt = Decimal(str(cand.amount))
                if abs(cand_amt - sms_amt) > _AMOUNT_TOLERANCE:
                    continue
                gap = abs(offset)
                if best is None or gap < best[0]:
                    best = (gap, cand)
                    if gap == 0:
                        break
            if best is not None and best[0] == 0:
                break

        if best is None:
            continue

        _gap_days, statement_row = best
        if await _existing_source_link(db, statement_row.id):
            matched_sms_ids.add(sms.id)
            continue

        db.add(
            TransactionSource(
                canonical_txn_id=statement_row.id,
                parsed_txn_id=None,
                match_confidence=0.95,
                match_method="sms_statement_match",
                is_primary=False,
            )
        )
        # Stamp the SMS row's source_evidence so the UI can show "confirmed
        # by statement on YYYY-MM-DD".
        evidence = dict(sms.source_evidence or {})
        evidence["confirmed_by_statement_id"] = str(statement_row.id)
        evidence["confirmed_at_date"] = statement_row.transaction_date.isoformat()
        sms.source_evidence = evidence
        matched_sms_ids.add(sms.id)
        matches.append(
            MatchResult(
                sms_canonical_id=sms.id,
                statement_canonical_id=statement_row.id,
                date_gap_days=int(_gap_days),
                amount_gap=abs(
                    Decimal(str(statement_row.amount)) - sms_amt
                ),
            )
        )

    await db.flush()
    report = MatchReport(
        matched_pairs=len(matches),
        sms_unmatched=len(sms_rows) - len(matched_sms_ids),
        matches=tuple(matches),
    )
    logger.info(
        "SMS↔statement match for user=%s fy=%s: matched=%d unmatched=%d",
        user_id,
        fy or "(all)",
        report.matched_pairs,
        report.sms_unmatched,
    )
    return report
