"""Cross-source deduplication engine — detects duplicate transactions across sources."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ledger.fingerprint import build_transaction_dedupe_fingerprint
from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.transaction_source import TransactionSource

logger = logging.getLogger(__name__)


class DedupEngine:
    """Finds duplicate transactions across different sources (statement, SMS, email).

    Three-tier matching:
    1. Exact reference match: same reference_number/UTR -> confidence 1.0
    2. Amount + date + fuzzy description: same amount, same date (+/-1 day),
       description similarity > 0.6 -> confidence 0.8-0.95
    3. Amount + date window (for SMS vs statement): same amount, date within 3 days
       -> confidence 0.6-0.8
    """

    async def find_duplicate(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        parsed_txn: ParsedTransaction,
        *,
        account_masked: str | None = None,
    ) -> tuple[CanonicalTransaction | None, float, str]:
        """Find a matching canonical transaction for the given parsed transaction.

        Returns (matching_canonical_txn, confidence, match_method) or (None, 0.0, "").
        """
        # Tier 0: Deterministic fingerprint (authoritative fast path)
        fingerprint = parsed_txn.dedupe_fingerprint or build_transaction_dedupe_fingerprint(
            user_id=user_id,
            account_masked=account_masked,
            transaction_date=parsed_txn.transaction_date,
            amount=float(parsed_txn.amount),
            description=parsed_txn.description_raw,
        )
        exact = await self._match_by_fingerprint(db, user_id, fingerprint)
        if exact is not None:
            return exact, 0.99, "fingerprint_exact"

        # Tier 1: Exact reference match
        if parsed_txn.reference_number:
            match = await self._match_by_reference(db, user_id, parsed_txn, account_masked)
            if match:
                return match, 1.0, "exact_ref"

        # Tier 2: Amount + date (+-1 day) + fuzzy description
        match, confidence = await self._match_by_amount_date_desc(
            db, user_id, parsed_txn, account_masked
        )
        if match:
            return match, confidence, "amount_date_desc"

        # Tier 3: Amount + wider date window (+-3 days) for cross-source
        match, confidence = await self._match_by_amount_date_window(
            db, user_id, parsed_txn, account_masked
        )
        if match:
            return match, confidence, "fuzzy"

        return None, 0.0, ""

    async def _match_by_fingerprint(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        fingerprint: str,
    ) -> CanonicalTransaction | None:
        result = await db.execute(
            select(CanonicalTransaction)
            .where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.dedupe_fingerprint == fingerprint,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _match_by_reference(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        parsed_txn: ParsedTransaction,
        account_masked: str | None,
    ) -> CanonicalTransaction | None:
        """Tier 1: Find canonical transaction with matching reference number."""
        ref = parsed_txn.reference_number
        if not ref:
            return None

        # Look for existing parsed transactions with the same reference
        query = (
            select(TransactionSource, CanonicalTransaction)
            .join(
                CanonicalTransaction,
                TransactionSource.canonical_txn_id == CanonicalTransaction.id,
            )
            .join(
                ParsedTransaction,
                TransactionSource.parsed_txn_id == ParsedTransaction.id,
            )
            .where(
                CanonicalTransaction.user_id == user_id,
                ParsedTransaction.reference_number == ref,
                ParsedTransaction.direction == parsed_txn.direction,
                ParsedTransaction.id != parsed_txn.id,
            )
        )
        if account_masked:
            query = query.where(
                (CanonicalTransaction.account_masked == account_masked)
                | (CanonicalTransaction.account_masked.is_(None))
            )
        result = await db.execute(query)
        row = result.first()
        if row:
            return row[1]  # The CanonicalTransaction
        return None

    async def _match_by_amount_date_desc(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        parsed_txn: ParsedTransaction,
        account_masked: str | None,
    ) -> tuple[CanonicalTransaction | None, float]:
        """Tier 2: Match by amount, date (+-1 day), and fuzzy description (>0.6)."""
        date_from = parsed_txn.transaction_date - timedelta(days=1)
        date_to = parsed_txn.transaction_date + timedelta(days=1)

        query = select(CanonicalTransaction).where(
            and_(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.amount == float(parsed_txn.amount),
                CanonicalTransaction.direction == parsed_txn.direction,
                CanonicalTransaction.transaction_date >= date_from,
                CanonicalTransaction.transaction_date <= date_to,
            )
        )
        if account_masked:
            query = query.where(
                (CanonicalTransaction.account_masked == account_masked)
                | (CanonicalTransaction.account_masked.is_(None))
            )
        result = await db.execute(query)
        candidates = result.scalars().all()

        best_match: CanonicalTransaction | None = None
        best_score = 0.0

        for canonical in candidates:
            similarity = SequenceMatcher(
                None,
                parsed_txn.description_raw.upper(),
                canonical.merchant_raw.upper(),
            ).ratio()

            if similarity > 0.6 and similarity > best_score:
                best_score = similarity
                best_match = canonical

        if best_match:
            # Map similarity 0.6-1.0 to confidence 0.8-0.95
            confidence = 0.8 + (best_score - 0.6) * (0.15 / 0.4)
            return best_match, min(confidence, 0.95)

        return None, 0.0

    async def _match_by_amount_date_window(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        parsed_txn: ParsedTransaction,
        account_masked: str | None,
    ) -> tuple[CanonicalTransaction | None, float]:
        """Tier 3: Match by amount and wider date window (+-3 days) for cross-source dedup."""
        date_from = parsed_txn.transaction_date - timedelta(days=3)
        date_to = parsed_txn.transaction_date + timedelta(days=3)

        query = select(CanonicalTransaction).where(
            and_(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.amount == float(parsed_txn.amount),
                CanonicalTransaction.direction == parsed_txn.direction,
                CanonicalTransaction.transaction_date >= date_from,
                CanonicalTransaction.transaction_date <= date_to,
            )
        )
        if account_masked:
            query = query.where(
                (CanonicalTransaction.account_masked == account_masked)
                | (CanonicalTransaction.account_masked.is_(None))
            )
        result = await db.execute(query)
        candidates = result.scalars().all()

        if not candidates:
            return None, 0.0

        # Pick the closest by date
        best_match: CanonicalTransaction | None = None
        best_day_diff = 999

        for canonical in candidates:
            day_diff = abs((canonical.transaction_date - parsed_txn.transaction_date).days)
            if day_diff < best_day_diff:
                best_day_diff = day_diff
                best_match = canonical

        if best_match:
            # Map day_diff 0-3 to confidence 0.8-0.6
            confidence = 0.8 - (best_day_diff * (0.2 / 3))
            return best_match, max(confidence, 0.6)

        return None, 0.0


async def merge_source(
    db: AsyncSession,
    canonical_txn: CanonicalTransaction,
    parsed_txn: ParsedTransaction,
    confidence: float,
    method: str,
) -> TransactionSource:
    """Link a parsed transaction to an existing canonical transaction as a secondary source."""
    source = TransactionSource(
        canonical_txn_id=canonical_txn.id,
        parsed_txn_id=parsed_txn.id,
        match_confidence=confidence,
        match_method=method,
        is_primary=False,
    )
    db.add(source)

    logger.info(
        "Merged source: parsed_txn %s -> canonical %s (confidence=%.2f, method=%s)",
        parsed_txn.id,
        canonical_txn.id,
        confidence,
        method,
    )

    return source
