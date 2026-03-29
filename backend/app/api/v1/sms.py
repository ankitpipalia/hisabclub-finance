from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.fingerprint import build_transaction_dedupe_fingerprint
from app.engines.ledger.merger import promote_to_canonical
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
