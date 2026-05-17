"""Multi-account transfer reconciliation surface.

Exposes the `transfer_matches` table that's already populated by
`reclassify_transfer_payments_for_user`. Surfaces matched pairs (HDFC → ICICI,
salary → savings, etc.) so the UI can show "this is one transfer, not two
separate transactions" and let the user confirm or reject the link.

Read-only listing + a single resolution endpoint for now. Resolution simply
updates `resolution_status` — it does not delete or merge canonical rows.
"""

from __future__ import annotations

from datetime import date as date_type, datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DbSession
from app.models.canonical_transaction import CanonicalTransaction
from app.models.transfer_match import TransferMatch

router = APIRouter()


class TransferLeg(BaseModel):
    transaction_id: str
    transaction_date: date_type
    amount: str
    bank_name: str | None
    account_masked: str | None
    direction: str
    description: str


class TransferMatchResponse(BaseModel):
    id: str
    match_type: str
    confidence: float
    resolution_status: str
    matched_at: datetime
    debit_leg: TransferLeg
    credit_leg: TransferLeg


class TransferMatchListResponse(BaseModel):
    items: list[TransferMatchResponse]
    total: int


class TransferResolutionRequest(BaseModel):
    decision: Literal["confirm", "reject"]


def _leg_from_canonical(txn: CanonicalTransaction) -> TransferLeg:
    return TransferLeg(
        transaction_id=str(txn.id),
        transaction_date=txn.transaction_date,
        amount=str(txn.amount),
        bank_name=txn.bank_name,
        account_masked=txn.account_masked,
        direction=txn.direction,
        description=txn.merchant_raw or txn.merchant_normalized or "",
    )


def _to_response(match: TransferMatch) -> TransferMatchResponse:
    return TransferMatchResponse(
        id=str(match.id),
        match_type=match.match_type,
        confidence=match.confidence,
        resolution_status=match.resolution_status,
        matched_at=match.matched_at,
        debit_leg=_leg_from_canonical(match.debit_transaction),
        credit_leg=_leg_from_canonical(match.credit_transaction),
    )


@router.get("", response_model=TransferMatchListResponse)
async def list_transfer_matches(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="One of: auto, confirmed, rejected. Defaults to all.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List transfer matches for the current user, most-recent first."""
    query = (
        select(TransferMatch)
        .where(TransferMatch.user_id == user.id)
        .options(
            selectinload(TransferMatch.debit_transaction),
            selectinload(TransferMatch.credit_transaction),
        )
        .order_by(desc(TransferMatch.matched_at))
        .limit(limit)
    )
    if status_filter:
        query = query.where(TransferMatch.resolution_status == status_filter)
    matches = (await db.execute(query)).scalars().all()
    items = [_to_response(m) for m in matches]
    return TransferMatchListResponse(items=items, total=len(items))


@router.post("/{match_id}/resolve", response_model=TransferMatchResponse)
async def resolve_transfer_match(
    match_id: str,
    request: TransferResolutionRequest,
    user: CurrentUser,
    db: DbSession,
):
    """User confirms or rejects an auto-detected transfer link.

    Does not delete or merge canonical rows; only updates resolution_status so
    future analytics can choose to ignore rejected matches.
    """
    match = (
        await db.execute(
            select(TransferMatch)
            .where(
                TransferMatch.id == match_id,
                TransferMatch.user_id == user.id,
            )
            .options(
                selectinload(TransferMatch.debit_transaction),
                selectinload(TransferMatch.credit_transaction),
            )
        )
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    new_status = "confirmed" if request.decision == "confirm" else "rejected"
    if match.resolution_status == new_status:
        return _to_response(match)

    match.resolution_status = new_status
    # Touch matched_at so the UI can sort by latest user activity if desired.
    match.matched_at = datetime.now(timezone.utc)
    await db.flush()
    return _to_response(match)
