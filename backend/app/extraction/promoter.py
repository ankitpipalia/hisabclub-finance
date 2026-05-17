from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.ledger.fingerprint import build_transaction_dedupe_fingerprint
from app.engines.ledger.review_helpers import create_review_task_for_canonical
from app.extraction.models import (
    BalanceWalkProblem,
    ExtractionSource,
    RawTransaction,
    StatementPeriod,
    ValidationStatus,
)
from app.extraction.validator import balance_walk_check, dedup_key, validate_transaction
from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.models.transaction_source import TransactionSource

logger = logging.getLogger(__name__)

LARGE_TRANSACTION_REVIEW_THRESHOLD = Decimal("100000.00")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]+")


@dataclass
class PromotionResult:
    promoted: list[uuid.UUID] = field(default_factory=list)
    duplicates: int = 0
    invalid: int = 0
    queued_for_review: list[uuid.UUID] = field(default_factory=list)
    parsed: list[uuid.UUID] = field(default_factory=list)
    balance_walk_passed: bool | None = None
    balance_walk_delta: Decimal | None = None
    balance_walk_problematic: list[BalanceWalkProblem] = field(default_factory=list)

    @property
    def total_in_review(self) -> int:
        return len(self.queued_for_review)


def compute_dedup_key(account_id: str | uuid.UUID, txn) -> str:
    return dedup_key(str(account_id), txn)


async def promote_validated_batch(
    *,
    raw_txns: list[RawTransaction],
    user_id: uuid.UUID,
    account_id: str | uuid.UUID,
    statement_id: uuid.UUID,
    statement_period: StatementPeriod | None,
    opening_balance: Decimal | None,
    closing_balance: Decimal | None,
    bank_name: str,
    account_type: str,
    account_masked: str | None,
    db: AsyncSession,
) -> PromotionResult:
    result = PromotionResult()

    validated = []
    for raw in raw_txns:
        txn = validate_transaction(raw, statement_period=statement_period)
        if txn.validation_status == ValidationStatus.INVALID:
            logger.warning(
                "Invalid extracted transaction skipped: errors=%s raw_description=%s",
                txn.validation_errors,
                raw.description_raw,
            )
            result.invalid += 1
            continue
        if txn.is_credit is None:
            if not settings.extraction_review_keeps_ambiguous_direction:
                logger.warning(
                    "Ambiguous-direction transaction skipped: errors=%s raw_description=%s",
                    txn.validation_errors,
                    raw.description_raw,
                )
                result.invalid += 1
                continue
            # Ambiguous direction defaults to debit so the row is reviewable and
            # correctable instead of silently disappearing from the audit trail.
            txn.is_credit = False
            txn.validation_status = ValidationStatus.NEEDS_REVIEW
            if "cr_dr_resolved" not in txn.validation_errors:
                txn.validation_errors.append("cr_dr_resolved")
        validated.append(txn)

    existing_keys = await _fetch_existing_dedup_keys(db=db, user_id=user_id)
    existing_reimport_signatures = await _fetch_existing_reimport_signatures(
        db=db,
        user_id=user_id,
        statement_id=statement_id,
    )
    new_txns = []
    for txn in validated:
        key = compute_dedup_key(account_id, txn)
        if key in existing_keys:
            result.duplicates += 1
            continue
        reimport_signature = _reimport_transaction_signature(
            transaction_date=txn.txn_date,
            amount=txn.amount,
            description=txn.description,
        )
        if reimport_signature in existing_reimport_signatures:
            result.duplicates += 1
            logger.info(
                "Duplicate skipped by exact-statement reimport signature: statement_id=%s",
                statement_id,
            )
            continue
        existing_keys.add(key)
        new_txns.append((txn, key))

    if not new_txns:
        return result

    walk_passed: bool | None = None
    problematic_keys: set[tuple] = set()
    if opening_balance is not None and closing_balance is not None:
        walk = balance_walk_check(
            [txn for txn, _key in new_txns],
            opening_balance=opening_balance,
            closing_balance=closing_balance,
        )
        walk_passed = walk.passed
        result.balance_walk_passed = walk.passed
        result.balance_walk_delta = walk.delta
        result.balance_walk_problematic = list(walk.problematic_txns)
        problematic_keys = {problem.identity_key() for problem in walk.problematic_txns}
        if not walk.passed:
            logger.warning(
                "Balance walk failed for statement %s: delta=%s problematic=%s",
                statement_id,
                walk.delta,
                walk.problematic_txns,
            )

    for txn, key in new_txns:
        parsed = _build_parsed_transaction(
            txn=txn,
            user_id=user_id,
            statement_id=statement_id,
            account_masked=account_masked,
        )
        db.add(parsed)
        await db.flush()
        result.parsed.append(parsed.id)

        canonical = await _create_canonical_transaction(
            db=db,
            user_id=user_id,
            parsed_txn=parsed,
            bank_name=bank_name,
            account_type=account_type,
            account_masked=account_masked,
            txn=txn,
            dedup_key_value=key,
            balance_walk_passed=walk_passed,
        )
        result.promoted.append(canonical.id)

        reasons = _review_reasons(txn, balance_walk_passed=walk_passed)
        if walk_passed is False:
            reasons.append("balance_walk_failed")
        if _balance_problem_key(txn) in problematic_keys:
            reasons.append("balance_walk_outlier")
        if reasons:
            await create_review_task_for_canonical(
                db,
                parsed=parsed,
                canonical=canonical,
                reasons=reasons,
                statement_id=statement_id,
                raw_evidence={
                    **txn.raw.source_evidence,
                    "balance_walk_passed": walk_passed,
                    "balance_walk_delta": str(result.balance_walk_delta)
                    if result.balance_walk_delta is not None
                    else "",
                },
            )
            result.queued_for_review.append(canonical.id)

    return result


async def _fetch_existing_dedup_keys(*, db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await db.execute(
        select(CanonicalTransaction.dedup_key).where(
            CanonicalTransaction.user_id == user_id,
            CanonicalTransaction.dedup_key.is_not(None),
        )
    )
    return {str(row[0]) for row in rows if row[0]}


async def _fetch_existing_reimport_signatures(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    statement_id: uuid.UUID,
) -> set[str]:
    """Return direction/account-insensitive signatures for exact re-imports.

    The normal dedup key includes direction to avoid merging a payment with its
    reversal. On a byte/semantic re-import of the same statement, LLM extraction
    can occasionally vary CR/DR or account-mask metadata. In that narrow case,
    matching the same source PDF hash (or stable statement fingerprint) lets us
    use a weaker row signature without weakening global dedup.
    """
    current = (
        await db.execute(
            select(Statement.statement_fingerprint, RawPdf.file_hash_sha256)
            .outerjoin(RawPdf, RawPdf.id == Statement.pdf_id)
            .where(
                Statement.id == statement_id,
                Statement.user_id == user_id,
            )
        )
    ).one_or_none()
    if current is None:
        return set()

    statement_fingerprint, file_hash = current
    if not statement_fingerprint and not file_hash:
        return set()

    match_clauses = []
    if statement_fingerprint:
        match_clauses.append(Statement.statement_fingerprint == statement_fingerprint)
    if file_hash:
        match_clauses.append(RawPdf.file_hash_sha256 == file_hash)

    rows = await db.execute(
        select(
            CanonicalTransaction.transaction_date,
            CanonicalTransaction.amount,
            CanonicalTransaction.merchant_raw,
        )
        .join(Statement, Statement.id == CanonicalTransaction.source_statement_id)
        .outerjoin(RawPdf, RawPdf.id == Statement.pdf_id)
        .where(
            CanonicalTransaction.user_id == user_id,
            CanonicalTransaction.source_statement_id.is_not(None),
            Statement.user_id == user_id,
            Statement.id != statement_id,
            or_(*match_clauses),
        )
    )
    signatures = set()
    for transaction_date, amount, description in rows:
        signatures.add(
            _reimport_transaction_signature(
                transaction_date=transaction_date,
                amount=amount,
                description=description,
            )
        )
    return signatures


def _reimport_transaction_signature(
    *,
    transaction_date: date,
    amount: Decimal | float | str,
    description: str,
) -> str:
    amount_decimal = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    amount_decimal = amount_decimal.copy_abs().quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    paise = int(amount_decimal * 100)
    normalized_description = _normalize_reimport_description(description)[:30]
    return "|".join([transaction_date.isoformat(), str(paise), normalized_description])


def _normalize_reimport_description(description: str) -> str:
    text = _NON_ALNUM_RE.sub(" ", str(description or "").upper())
    return " ".join(text.split())


def _build_parsed_transaction(
    *,
    txn,
    user_id: uuid.UUID,
    statement_id: uuid.UUID,
    account_masked: str | None,
) -> ParsedTransaction:
    direction = "credit" if txn.is_credit else "debit"
    return ParsedTransaction(
        user_id=user_id,
        source_type="statement",
        source_id=statement_id,
        statement_id=statement_id,
        transaction_date=txn.txn_date,
        posting_date=None,
        description_raw=txn.description,
        amount=txn.amount,
        direction=direction,
        currency="INR",
        foreign_amount=None,
        foreign_currency=None,
        reference_number=_clean_reference(txn.raw.source_evidence.get("reference_number")),
        confidence=max(0.0, min(1.0, float(txn.raw.confidence or 0.0))),
        is_quarantined=False,
        extraction_method=_legacy_extraction_method(txn.raw.source),
        line_number=txn.raw.char_offset or None,
        dedupe_fingerprint=build_transaction_dedupe_fingerprint(
            user_id=user_id,
            account_masked=account_masked,
            transaction_date=txn.txn_date,
            amount=float(txn.amount),
            description=txn.description,
        ),
    )


async def _create_canonical_transaction(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    parsed_txn: ParsedTransaction,
    bank_name: str,
    account_type: str,
    account_masked: str | None,
    txn,
    dedup_key_value: str,
    balance_walk_passed: bool | None,
) -> CanonicalTransaction:
    merchant_id, category_id, merchant_normalized = await _normalize_and_categorize(
        db, parsed_txn.description_raw
    )
    category_source = "auto"
    if category_id is None:
        inferred_category_id, inferred_source = await _infer_uncategorized_category(
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
        transaction_nature=_infer_transaction_nature(
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
        dedupe_fingerprint=parsed_txn.dedupe_fingerprint,
        foreign_amount=parsed_txn.foreign_amount,
        foreign_currency=parsed_txn.foreign_currency,
        extraction_source=txn.raw.source.value,
        extraction_confidence=float(txn.raw.confidence or 0.0),
        source_statement_id=parsed_txn.statement_id,
        source_page_number=txn.raw.page_number,
        source_char_offset=txn.raw.char_offset,
        source_evidence=_json_safe(txn.raw.source_evidence),
        dedup_key=dedup_key_value,
        validation_status=txn.validation_status.value,
        validation_errors=txn.validation_errors or None,
        balance_walk_passed=balance_walk_passed,
    )
    db.add(canonical)
    await db.flush()
    db.add(
        TransactionSource(
            canonical_txn_id=canonical.id,
            parsed_txn_id=parsed_txn.id,
            match_confidence=1.0,
            match_method="typed_pipeline",
            is_primary=True,
        )
    )
    return canonical


def _review_reasons(txn, *, balance_walk_passed: bool | None) -> list[str]:
    reasons: list[str] = []
    if (txn.raw.confidence or 0.0) < 0.75:
        reasons.append("low_confidence")
    ai_sourced = txn.raw.source in {
        ExtractionSource.LLM_TEXT,
        ExtractionSource.LLM_VISION,
        ExtractionSource.OCR_LLM,
    }
    if ai_sourced:
        reasons.append("ai_sourced")
    if txn.amount > LARGE_TRANSACTION_REVIEW_THRESHOLD and (
        ai_sourced or balance_walk_passed is not True
    ):
        reasons.append("large_amount")
    if txn.validation_status in {ValidationStatus.LOW_CONFIDENCE, ValidationStatus.NEEDS_REVIEW}:
        reasons.append("needs_review")
    return list(dict.fromkeys(reasons))


def _balance_problem_key(txn) -> tuple:
    return (txn.txn_date, txn.amount, str(txn.description or "")[:40])


def _legacy_extraction_method(source: ExtractionSource) -> str:
    if source == ExtractionSource.LLM_TEXT:
        return "llm"
    if source == ExtractionSource.LLM_VISION:
        return "vision"
    if source == ExtractionSource.OCR_LLM:
        return "ocr"
    if source == ExtractionSource.MANUAL:
        return "manual"
    if source == ExtractionSource.SMS:
        return "sms_regex"
    return "template"


async def _normalize_and_categorize(db: AsyncSession, description: str):
    from app.engines.ledger.merchant_normalizer import normalize_and_categorize

    return await normalize_and_categorize(db, description)


async def _infer_uncategorized_category(**kwargs):
    from app.engines.ledger.category_enrichment import infer_uncategorized_category

    return await infer_uncategorized_category(**kwargs)


def _infer_transaction_nature(description: str, direction: str, account_type: str) -> str:
    from app.engines.ledger.nature import infer_transaction_nature

    return infer_transaction_nature(description, direction, account_type)


def _clean_reference(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _json_safe(payload: dict[str, Any]) -> dict[str, str]:
    return {str(key): _stringify_json_value(value) for key, value in payload.items()}


def _stringify_json_value(value: Any) -> str:
    if isinstance(value, (date, Decimal, uuid.UUID)):
        return str(value)
    return str(value) if value is not None else ""
