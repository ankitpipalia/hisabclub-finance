"""Ledger engine — promotes parsed transactions to canonical transactions with dedup."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ledger.category_enrichment import infer_uncategorized_category
from app.engines.ledger.dedup import DedupEngine, merge_source
from app.engines.ledger.fingerprint import build_transaction_dedupe_fingerprint
from app.engines.ledger.merchant_normalizer import normalize_and_categorize
from app.engines.ledger.nature import infer_transaction_nature
from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.transaction_source import TransactionSource

logger = logging.getLogger(__name__)

_dedup_engine = DedupEngine()


async def promote_to_canonical(
    db: AsyncSession,
    user_id: uuid.UUID,
    parsed_txn: ParsedTransaction,
    bank_name: str,
    account_type: str,
    account_masked: str | None,
    *,
    validation_status: str = "valid",
    validation_errors: list[str] | None = None,
    balance_walk_passed: bool | None = None,
) -> CanonicalTransaction:
    """Create or merge a canonical transaction from a parsed transaction.

    1. First checks for duplicates via DedupEngine.
    2. If a duplicate is found, merges the source into the existing canonical.
    3. If no duplicate, creates a new canonical transaction.
    """
    # Step 1: Check for duplicates
    existing, confidence, method = await _dedup_engine.find_duplicate(
        db, user_id, parsed_txn, account_masked=account_masked
    )

    if existing is not None:
        # Step 2: Duplicate found — merge source
        logger.info(
            "Dedup match: parsed_txn %s matches canonical %s "
            "(confidence=%.2f, method=%s)",
            parsed_txn.id,
            existing.id,
            confidence,
            method,
        )
        await merge_source(db, existing, parsed_txn, confidence, method)
        setattr(existing, "_hc_was_dedup_merge", True)
        return existing

    # Step 3: No duplicate — create new canonical
    # Try to normalize merchant and find category
    merchant_id, category_id, merchant_normalized = await normalize_and_categorize(
        db, parsed_txn.description_raw
    )
    category_source = "auto"
    if category_id is None:
        inferred_category_id, inferred_source = await infer_uncategorized_category(
            db=db,
            user_id=user_id,
            description_raw=parsed_txn.description_raw,
            amount=float(parsed_txn.amount),
        )
        if inferred_category_id is not None:
            category_id = inferred_category_id
            category_source = inferred_source

    canonical = CanonicalTransaction(
        user_id=user_id,
        transaction_date=parsed_txn.transaction_date,
        posting_date=parsed_txn.posting_date,
        amount=parsed_txn.amount,
        direction=parsed_txn.direction,
        currency=parsed_txn.currency,
        transaction_nature=infer_transaction_nature(
            parsed_txn.description_raw,
            parsed_txn.direction,
            account_type,
        ),
        merchant_raw=parsed_txn.description_raw,
        merchant_normalized=merchant_normalized,
        merchant_id=merchant_id,
        category_id=category_id,
        category_source=category_source,
        account_masked=account_masked,
        bank_name=bank_name,
        account_type=account_type,
        dedupe_fingerprint=parsed_txn.dedupe_fingerprint
        or build_transaction_dedupe_fingerprint(
            user_id=user_id,
            account_masked=account_masked,
            transaction_date=parsed_txn.transaction_date,
            amount=parsed_txn.amount,
            description=parsed_txn.description_raw,
        ),
        foreign_amount=parsed_txn.foreign_amount,
        foreign_currency=parsed_txn.foreign_currency,
        extraction_source=_canonical_extraction_source(parsed_txn),
        extraction_confidence=float(parsed_txn.confidence or 0.0),
        source_statement_id=parsed_txn.statement_id,
        source_page_number=1 if parsed_txn.statement_id else None,
        source_char_offset=parsed_txn.line_number or 0,
        source_evidence={
            "source_type": parsed_txn.source_type,
            "source_id": str(parsed_txn.source_id),
            "statement_id": str(parsed_txn.statement_id) if parsed_txn.statement_id else "",
            "description_raw": parsed_txn.description_raw,
            "reference_number": parsed_txn.reference_number or "",
            "extraction_method": parsed_txn.extraction_method,
        },
        validation_status=validation_status,
        validation_errors=validation_errors or None,
        balance_walk_passed=balance_walk_passed,
    )
    db.add(canonical)
    await db.flush()
    setattr(canonical, "_hc_was_dedup_merge", False)

    # Link source
    source = TransactionSource(
        canonical_txn_id=canonical.id,
        parsed_txn_id=parsed_txn.id,
        match_confidence=1.0,
        match_method="single_source",
        is_primary=True,
    )
    db.add(source)
    await db.flush()

    logger.info(
        "Promoted parsed_txn %s to canonical %s with validation_status=%s",
        parsed_txn.id,
        canonical.id,
        validation_status,
    )

    return canonical


def _canonical_extraction_source(parsed_txn: ParsedTransaction) -> str:
    if parsed_txn.source_type == "sms":
        return "sms"
    if parsed_txn.source_type == "manual":
        return "manual"
    method = (parsed_txn.extraction_method or "").strip().lower()
    if method == "vision":
        return "llm_vision"
    if method == "llm":
        return "llm_text"
    if method == "ocr":
        return "ocr_llm"
    return "template" if parsed_txn.source_type == "statement" else "manual"
