from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from app.dependencies import CurrentUser, DbSession
from app.engines.insights.net_worth import (
    build_manual_position_key,
    build_net_worth_history,
    summarize_latest_positions,
    sync_statement_balance_snapshots,
)
from app.models.balance_snapshot import BalanceSnapshot
from app.schemas.net_worth import (
    BalanceSnapshotResponse,
    ManualBalanceSnapshotCreateRequest,
    NetWorthHistoryPoint,
    NetWorthOverviewResponse,
    NetWorthTotals,
)

router = APIRouter()


def _to_snapshot_response(snapshot: BalanceSnapshot) -> BalanceSnapshotResponse:
    return BalanceSnapshotResponse(
        id=str(snapshot.id),
        account_id=str(snapshot.account_id) if snapshot.account_id else None,
        statement_id=str(snapshot.statement_id) if snapshot.statement_id else None,
        position_key=snapshot.position_key,
        label=snapshot.label,
        source_kind=snapshot.source_kind,
        entry_kind=snapshot.entry_kind,
        asset_type=snapshot.asset_type,
        institution_name=snapshot.institution_name,
        account_masked=snapshot.account_masked,
        currency=snapshot.currency,
        balance=round(float(snapshot.balance), 2),
        as_of_date=snapshot.as_of_date,
        is_active=snapshot.is_active,
        metadata_json=snapshot.metadata_json,
    )


@router.get("/overview", response_model=NetWorthOverviewResponse)
async def get_net_worth_overview(
    user: CurrentUser,
    db: DbSession,
    months: int = Query(12, ge=3, le=60),
):
    await sync_statement_balance_snapshots(db, user_id=user.id)
    await db.flush()

    snapshots = (
        await db.execute(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.user_id == user.id, BalanceSnapshot.is_active == True)  # noqa: E712
            .order_by(BalanceSnapshot.as_of_date.asc(), BalanceSnapshot.created_at.asc())
        )
    ).scalars().all()
    positions, totals = summarize_latest_positions(snapshots)
    history = build_net_worth_history(snapshots, months=months)
    manual_snapshots = [
        snapshot
        for snapshot in reversed(snapshots)
        if snapshot.source_kind == "manual"
    ][:20]

    return NetWorthOverviewResponse(
        totals=NetWorthTotals(**totals),
        history=[NetWorthHistoryPoint(**point) for point in history],
        positions=[_to_snapshot_response(snapshot) for snapshot in positions],
        manual_snapshots=[_to_snapshot_response(snapshot) for snapshot in manual_snapshots],
    )


@router.post("/manual-snapshots", response_model=BalanceSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_snapshot(
    request: ManualBalanceSnapshotCreateRequest,
    user: CurrentUser,
    db: DbSession,
):
    entry_kind = request.entry_kind.strip().lower()
    if entry_kind not in {"asset", "liability"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid entry_kind.")
    label = request.label.strip()
    if not label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label is required.")
    currency = (request.currency or "INR").strip().upper() or "INR"

    snapshot = BalanceSnapshot(
        user_id=user.id,
        account_id=None,
        statement_id=None,
        position_key=request.position_key or build_manual_position_key(label, entry_kind, request.asset_type),
        label=label,
        source_kind="manual",
        entry_kind=entry_kind,
        asset_type=request.asset_type.strip().lower(),
        institution_name=request.institution_name.strip() if request.institution_name else None,
        account_masked=request.account_masked.strip() if request.account_masked else None,
        currency=currency,
        balance=round(float(request.balance), 2),
        as_of_date=request.as_of_date,
        is_active=True,
        metadata_json=request.metadata_json,
    )
    db.add(snapshot)
    await db.flush()
    return _to_snapshot_response(snapshot)


@router.delete("/manual-snapshots/{snapshot_id}", response_model=BalanceSnapshotResponse)
async def delete_manual_snapshot(snapshot_id: str, user: CurrentUser, db: DbSession):
    snapshot = (
        await db.execute(
            select(BalanceSnapshot).where(
                BalanceSnapshot.id == snapshot_id,
                BalanceSnapshot.user_id == user.id,
                BalanceSnapshot.source_kind == "manual",
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    response = _to_snapshot_response(snapshot)
    await db.execute(delete(BalanceSnapshot).where(BalanceSnapshot.id == snapshot.id))
    return response
