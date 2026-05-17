from fastapi import APIRouter
from sqlalchemy import select

from app.config import settings
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
    """Import a batch of SMS messages, parse them, and promote to canonical transactions."""
    accepted = 0
    duplicates = 0
    errors = 0
    details: list[SmsBatchItemResult] = []

    for item in request.items:
        try:
            # Check for duplicate by sms_hash for this user
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

            # Insert into raw_sms
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

            if settings.sms_typed_validation_enabled:
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
                continue

            # Create ParsedTransaction
            parsed_txn = ParsedTransaction(
                user_id=user.id,
                source_type="sms",
                source_id=raw_sms.id,
                transaction_date=item.sms_timestamp.date(),
                description_raw=item.description or item.body,
                amount=item.amount or 0,
                direction=item.direction or "debit",
                currency="INR",
                reference_number=item.reference_number,
                upi_id=item.upi_id,
                confidence=item.confidence,
                extraction_method="sms_regex",
                dedupe_fingerprint=build_transaction_dedupe_fingerprint(
                    user_id=user.id,
                    account_masked=item.account_masked,
                    transaction_date=item.sms_timestamp.date(),
                    amount=item.amount or 0,
                    description=item.description or item.body,
                ),
            )
            db.add(parsed_txn)
            await db.flush()

            # Promote to canonical
            canonical = await promote_to_canonical(
                db=db,
                user_id=user.id,
                parsed_txn=parsed_txn,
                bank_name=item.bank_name or "Unknown",
                account_type=item.account_type or "savings",
                account_masked=item.account_masked,
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
