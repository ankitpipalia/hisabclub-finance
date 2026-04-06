from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance_snapshot import BalanceSnapshot
from app.models.statement import Statement

_SUPPORTED_STATEMENT_ACCOUNT_TYPES = {"savings", "current", "credit_card"}


@dataclass
class StatementSnapshotSeed:
    position_key: str
    label: str
    source_kind: str
    entry_kind: str
    asset_type: str
    institution_name: str | None
    account_masked: str | None
    currency: str
    balance: float
    as_of_date: date
    metadata_json: dict[str, object]


def build_position_key(*parts: str | None) -> str:
    tokens = [re.sub(r"[^a-z0-9]+", "-", (part or "").strip().lower()) for part in parts]
    normalized = "-".join(token.strip("-") for token in tokens if token.strip("-"))
    return normalized or "position"


def build_manual_position_key(label: str, entry_kind: str, asset_type: str) -> str:
    return build_position_key(entry_kind, asset_type, label)


def build_statement_snapshot_seed(statement: Statement) -> StatementSnapshotSeed | None:
    account_type = (statement.account_type or "").strip().lower()
    if account_type not in _SUPPORTED_STATEMENT_ACCOUNT_TYPES:
        return None

    balance: float | None
    entry_kind: str
    asset_type: str
    if account_type == "credit_card":
        if statement.total_amount_due is None:
            return None
        balance = abs(float(statement.total_amount_due))
        entry_kind = "liability"
        asset_type = "credit_card_due"
    else:
        if statement.closing_balance is None:
            return None
        balance = float(statement.closing_balance)
        entry_kind = "asset"
        asset_type = "cash"

    as_of_date = statement.statement_period_end
    if as_of_date is None and statement.parsed_at is not None:
        as_of_date = statement.parsed_at.date()
    if as_of_date is None:
        as_of_date = statement.created_at.date()
    label_parts = [statement.bank_name, account_type.replace("_", " ").title()]
    if statement.account_number_masked:
        label_parts.append(statement.account_number_masked)
    label = " ".join(part for part in label_parts if part)
    position_key = (
        f"account:{statement.account_id}"
        if statement.account_id
        else build_position_key(
            "statement",
            statement.bank_name,
            account_type,
            statement.account_number_masked,
        )
    )
    return StatementSnapshotSeed(
        position_key=position_key,
        label=label,
        source_kind="statement",
        entry_kind=entry_kind,
        asset_type=asset_type,
        institution_name=statement.bank_name,
        account_masked=statement.account_number_masked,
        currency=statement.currency or "INR",
        balance=round(balance, 2),
        as_of_date=as_of_date,
        metadata_json={
            "statement_id": str(statement.id),
            "account_type": statement.account_type,
            "statement_period_start": statement.statement_period_start.isoformat()
            if statement.statement_period_start
            else None,
            "statement_period_end": statement.statement_period_end.isoformat()
            if statement.statement_period_end
            else None,
            "parse_status": statement.parse_status,
        },
    )


async def upsert_statement_balance_snapshot(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    statement: Statement,
) -> BalanceSnapshot | None:
    seed = build_statement_snapshot_seed(statement)
    if seed is None:
        return None

    existing = (
        await db.execute(
            select(BalanceSnapshot).where(
                BalanceSnapshot.user_id == user_id,
                BalanceSnapshot.statement_id == statement.id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = BalanceSnapshot(
            user_id=user_id,
            account_id=statement.account_id,
            statement_id=statement.id,
            position_key=seed.position_key,
            label=seed.label,
            source_kind=seed.source_kind,
            entry_kind=seed.entry_kind,
            asset_type=seed.asset_type,
            institution_name=seed.institution_name,
            account_masked=seed.account_masked,
            currency=seed.currency,
            balance=seed.balance,
            as_of_date=seed.as_of_date,
            is_active=statement.is_active,
            metadata_json=seed.metadata_json,
        )
        db.add(existing)
    else:
        existing.account_id = statement.account_id
        existing.position_key = seed.position_key
        existing.label = seed.label
        existing.source_kind = seed.source_kind
        existing.entry_kind = seed.entry_kind
        existing.asset_type = seed.asset_type
        existing.institution_name = seed.institution_name
        existing.account_masked = seed.account_masked
        existing.currency = seed.currency
        existing.balance = seed.balance
        existing.as_of_date = seed.as_of_date
        existing.is_active = statement.is_active
        existing.metadata_json = seed.metadata_json
    await db.flush()
    return existing


async def sync_statement_balance_snapshots(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    statements = (
        await db.execute(
            select(Statement)
            .where(
                Statement.user_id == user_id,
                Statement.is_active == True,  # noqa: E712
                Statement.account_type.in_(tuple(_SUPPORTED_STATEMENT_ACCOUNT_TYPES)),
                Statement.parse_status.in_(("parsed", "partial", "review_required")),
            )
            .order_by(Statement.statement_period_end.asc(), Statement.created_at.asc())
        )
    ).scalars().all()

    synced = 0
    for statement in statements:
        snapshot = await upsert_statement_balance_snapshot(db, user_id=user_id, statement=statement)
        if snapshot is not None:
            synced += 1
    return synced


def build_net_worth_history(
    snapshots: Iterable[BalanceSnapshot],
    *,
    months: int,
) -> list[dict[str, object]]:
    ordered = sorted(snapshots, key=lambda row: (row.as_of_date, row.created_at, str(row.id)))
    if not ordered:
        return []

    latest_date = ordered[-1].as_of_date
    cutoff = latest_date - timedelta(days=max(months - 1, 0) * 31)
    active_positions: dict[str, BalanceSnapshot] = {}
    history: list[dict[str, object]] = []

    for snapshot in ordered:
        active_positions[snapshot.position_key] = snapshot
        if snapshot.as_of_date < cutoff:
            continue

        assets = 0.0
        liabilities = 0.0
        for position in active_positions.values():
            amount = float(position.balance)
            if position.entry_kind == "liability":
                liabilities += amount
            else:
                assets += amount
        history.append(
            {
                "as_of_date": snapshot.as_of_date,
                "assets": round(assets, 2),
                "liabilities": round(liabilities, 2),
                "net_worth": round(assets - liabilities, 2),
            }
        )
    deduped: list[dict[str, object]] = []
    for point in history:
        if deduped and deduped[-1]["as_of_date"] == point["as_of_date"]:
            deduped[-1] = point
        else:
            deduped.append(point)
    return deduped


def summarize_latest_positions(
    snapshots: Iterable[BalanceSnapshot],
) -> tuple[list[BalanceSnapshot], dict[str, float | int | str | None]]:
    latest_by_position: dict[str, BalanceSnapshot] = {}
    for snapshot in sorted(snapshots, key=lambda row: (row.as_of_date, row.created_at, str(row.id))):
        latest_by_position[snapshot.position_key] = snapshot

    positions = sorted(
        latest_by_position.values(),
        key=lambda row: (row.entry_kind != "asset", row.label.lower(), row.as_of_date),
    )
    assets = round(
        sum(float(row.balance) for row in positions if row.entry_kind == "asset"),
        2,
    )
    liabilities = round(
        sum(float(row.balance) for row in positions if row.entry_kind == "liability"),
        2,
    )
    latest_date = max((row.as_of_date for row in positions), default=None)
    summary = {
        "assets": assets,
        "liabilities": liabilities,
        "net_worth": round(assets - liabilities, 2),
        "positions_count": len(positions),
        "manual_positions_count": sum(1 for row in positions if row.source_kind == "manual"),
        "latest_snapshot_date": latest_date.isoformat() if latest_date else None,
    }
    return positions, summary
