from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.fingerprint import build_transaction_dedupe_fingerprint
from app.engines.ledger.merger import promote_to_canonical
from app.engines.ledger.review_helpers import create_review_task_for_canonical
from app.extraction.adapter import dict_to_raw_transaction
from app.extraction.models import ExtractionSource, ValidationStatus
from app.extraction.validator import parse_decimal_amount, validate_transaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.raw_sms import RawSms
from app.schemas.sms import (
    SmsBatchItemResult,
    SmsBatchRequest,
    SmsBatchResponse,
)

router = APIRouter()


@router.post("/batch", response_model=SmsBatchResponse)
async def sms_batch_import(
    request: SmsBatchRequest,
    user: CurrentUser,
    db: DbSession,
):
    """Import a batch of SMS messages, parse them, and promote to canonical transactions.

    Every SMS in the batch goes through the typed extraction validator
    (`app.extraction.validator.validate_transaction`). Rows that fail
    validation (INVALID) become "error" items and are NOT promoted. Rows that
    are LOW_CONFIDENCE / NEEDS_REVIEW promote to canonical with the matching
    `validation_status` preserved, then receive a review task so a human can
    confirm or correct them. The legacy permissive bypass that used to run
    when `sms_typed_validation_enabled` was False has been removed (Phase 1,
    master_plan_2026.md §26).
    """
    accepted = 0
    duplicates = 0
    errors = 0
    details: list[SmsBatchItemResult] = []

    for item in request.items:
        try:
            result = await db.execute(
                select(RawSms).where(
                    RawSms.user_id == user.id,
                    RawSms.sms_hash == item.sms_hash,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                duplicates += 1
                details.append(
                    SmsBatchItemResult(
                        sms_hash=item.sms_hash,
                        status="duplicate",
                    )
                )
                continue

            raw_sms = RawSms(
                user_id=user.id,
                sms_hash=item.sms_hash,
                sender_address=item.sender_address,
                sender_id=item.sender_id,
                body=item.body,
                sms_timestamp=item.sms_timestamp,
                classification=item.classification,
                bank_name=item.bank_name,
                account_masked=item.account_masked,
                amount=item.amount,
                direction=item.direction,
                confidence=item.confidence,
                device_id=request.device_id,
            )
            db.add(raw_sms)
            await db.flush()

            raw_txn = dict_to_raw_transaction(
                {
                    "date": item.sms_timestamp.strftime("%d/%m/%Y"),
                    "description": item.description or item.body,
                    "amount": str(item.amount or ""),
                    "direction": item.direction or "",
                    "confidence": item.confidence,
                    "reference_number": item.reference_number or "",
                    "sms_hash": item.sms_hash,
                    "sender_id": item.sender_id or item.sender_address,
                },
                source=ExtractionSource.SMS,
                confidence=item.confidence,
            )
            validated = validate_transaction(raw_txn)
            if validated.validation_status == ValidationStatus.INVALID:
                errors += 1
                details.append(
                    SmsBatchItemResult(
                        sms_hash=item.sms_hash,
                        status="error",
                        error=";".join(validated.validation_errors),
                    )
                )
                continue

            is_credit = validated.is_credit
            validation_errors = list(validated.validation_errors)
            validation_status = validated.validation_status
            if is_credit is None:
                # Ambiguous direction: default to debit and flag for review so
                # the row is auditable instead of silently dropped.
                is_credit = False
                validation_status = ValidationStatus.NEEDS_REVIEW
                if "cr_dr_resolved" not in validation_errors:
                    validation_errors.append("cr_dr_resolved")

            parsed_amount = parse_decimal_amount(item.amount and str(item.amount))
            if parsed_amount is None:
                parsed_amount = validated.amount

            parsed_txn = ParsedTransaction(
                user_id=user.id,
                source_type="sms",
                source_id=raw_sms.id,
                transaction_date=validated.txn_date,
                description_raw=validated.description,
                amount=parsed_amount,
                direction="credit" if is_credit else "debit",
                currency="INR",
                reference_number=item.reference_number,
                upi_id=item.upi_id,
                confidence=item.confidence,
                is_quarantined=validation_status
                in {ValidationStatus.LOW_CONFIDENCE, ValidationStatus.NEEDS_REVIEW},
                extraction_method="sms_regex",
                dedupe_fingerprint=build_transaction_dedupe_fingerprint(
                    user_id=user.id,
                    account_masked=item.account_masked,
                    transaction_date=validated.txn_date,
                    amount=parsed_amount,
                    description=validated.description,
                ),
            )
            db.add(parsed_txn)
            await db.flush()

            canonical = await promote_to_canonical(
                db=db,
                user_id=user.id,
                parsed_txn=parsed_txn,
                bank_name=item.bank_name or "Unknown",
                account_type=item.account_type or "savings",
                account_masked=item.account_masked,
                validation_status=validation_status.value,
                validation_errors=validation_errors or None,
            )
            if validation_status in {
                ValidationStatus.LOW_CONFIDENCE,
                ValidationStatus.NEEDS_REVIEW,
            }:
                await create_review_task_for_canonical(
                    db,
                    parsed=parsed_txn,
                    canonical=canonical,
                    reasons=validation_errors or [validation_status.value],
                    statement_id=None,
                    raw_evidence=raw_txn.source_evidence,
                )

            accepted += 1
            details.append(
                SmsBatchItemResult(
                    sms_hash=item.sms_hash,
                    status="accepted",
                    transaction_id=str(canonical.id),
                )
            )

        except Exception as e:
            errors += 1
            details.append(
                SmsBatchItemResult(
                    sms_hash=item.sms_hash,
                    status="error",
                    error=str(e),
                )
            )

    await db.commit()

    return SmsBatchResponse(
        accepted=accepted,
        duplicates=duplicates,
        errors=errors,
        details=details,
    )


class SmsMatchResponse(BaseModel):
    fy: str | None
    matched_pairs: int
    sms_unmatched: int


@router.post("/match", response_model=SmsMatchResponse)
async def sms_match_to_statements(
    user: CurrentUser,
    db: DbSession,
    fy: str | None = None,
):
    """Run the SMS↔statement matcher for the user.

    If `fy` is provided (e.g. "FY24-25"), restrict to that window. Otherwise
    matches across the entire user history. Useful as a manual trigger from
    the dashboard; also scheduled daily by the job runner.
    """
    from app.engines.ledger.sms_statement_match import match_sms_to_statements

    report = await match_sms_to_statements(db, user.id, fy)
    await db.commit()
    return SmsMatchResponse(
        fy=fy,
        matched_pairs=report.matched_pairs,
        sms_unmatched=report.sms_unmatched,
    )
