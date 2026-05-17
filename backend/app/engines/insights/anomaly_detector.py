"""Anomaly detection over a user's expense history.

Flags recent debit transactions whose amount is more than `sigma` standard
deviations above the rolling per-category mean, and the first-time-seen large
merchant case (no prior history with this merchant_normalized + amount above a
floor).

Lightweight and deterministic — no LLM. Designed to run on-request for the
dashboard, not as a background job.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, pstdev
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category


@dataclass(frozen=True)
class AnomalyFinding:
    transaction_id: uuid.UUID
    transaction_date: date
    amount: Decimal
    merchant: str
    category_id: uuid.UUID | None
    category_name: str | None
    bank_name: str | None
    reason: str  # "category_spike" | "new_large_merchant"
    detail: str  # human-readable explanation
    expected_mean: Decimal | None  # for category_spike
    expected_max: Decimal | None  # mean + sigma*stddev cutoff
    deviation_ratio: float | None  # how many sigma above the mean

    def to_dict(self) -> dict:
        return {
            "transaction_id": str(self.transaction_id),
            "transaction_date": self.transaction_date.isoformat(),
            "amount": str(self.amount),
            "merchant": self.merchant,
            "category_id": str(self.category_id) if self.category_id else None,
            "category_name": self.category_name,
            "bank_name": self.bank_name,
            "reason": self.reason,
            "detail": self.detail,
            "expected_mean": str(self.expected_mean) if self.expected_mean is not None else None,
            "expected_max": str(self.expected_max) if self.expected_max is not None else None,
            "deviation_ratio": (
                round(self.deviation_ratio, 2) if self.deviation_ratio is not None else None
            ),
        }


async def find_recent_anomalies(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    window_days: int = 30,
    history_days: int = 90,
    sigma: float = 2.0,
    new_merchant_floor: Decimal = Decimal("5000.00"),
    limit: int = 50,
) -> list[AnomalyFinding]:
    """Return anomalies in the last `window_days` for a user.

    Two detectors run in parallel:
    1. category_spike — txn amount > mean + sigma*stddev for that category
       over `history_days`.
    2. new_large_merchant — first time we've ever seen this merchant_normalized
       AND amount >= `new_merchant_floor`.

    The user is presumed to want this surfaced quickly, so we cap at `limit`
    and sort most-recent first.
    """
    today = date.today()
    window_start = today - timedelta(days=window_days)
    history_start = today - timedelta(days=history_days)

    rows = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.is_excluded == False,  # noqa: E712
                CanonicalTransaction.direction == "debit",
                CanonicalTransaction.transaction_nature == "expense",
                CanonicalTransaction.transaction_date >= history_start,
            )
            .order_by(CanonicalTransaction.transaction_date.asc())
        )
    ).all()
    if not rows:
        return []

    history_by_category: dict[uuid.UUID | None, list[Decimal]] = defaultdict(list)
    history_by_merchant: dict[str, list[date]] = defaultdict(list)
    in_window: list[tuple[CanonicalTransaction, str | None]] = []
    for txn, category_name in rows:
        history_by_category[txn.category_id].append(Decimal(str(txn.amount)))
        if txn.merchant_normalized:
            history_by_merchant[txn.merchant_normalized.upper()].append(
                txn.transaction_date
            )
        if txn.transaction_date >= window_start:
            in_window.append((txn, category_name))

    findings: list[AnomalyFinding] = []
    for txn, category_name in in_window:
        amount = Decimal(str(txn.amount))
        cat_amounts = history_by_category.get(txn.category_id, [])
        finding = _category_spike(
            txn, category_name, amount, cat_amounts, sigma
        ) or _new_large_merchant(
            txn,
            category_name,
            amount,
            history_by_merchant,
            window_start,
            new_merchant_floor,
        )
        if finding is not None:
            findings.append(finding)

    findings.sort(key=lambda f: (f.transaction_date, f.amount), reverse=True)
    return findings[:limit]


def _category_spike(
    txn: CanonicalTransaction,
    category_name: str | None,
    amount: Decimal,
    cat_amounts: Iterable[Decimal],
    sigma: float,
) -> AnomalyFinding | None:
    # Need a meaningful baseline. < 5 prior values is too noisy to flag.
    values = [v for v in cat_amounts if v != amount]
    if len(values) < 5:
        return None
    avg = Decimal(str(mean(float(v) for v in values)))
    sd = Decimal(str(pstdev(float(v) for v in values)))
    if sd == 0:
        return None
    cutoff = avg + Decimal(str(sigma)) * sd
    if amount <= cutoff:
        return None
    deviation = float((amount - avg) / sd) if sd > 0 else None
    label = category_name or "uncategorized"
    return AnomalyFinding(
        transaction_id=txn.id,
        transaction_date=txn.transaction_date,
        amount=amount,
        merchant=txn.merchant_normalized or txn.merchant_raw or "Unknown",
        category_id=txn.category_id,
        category_name=category_name,
        bank_name=txn.bank_name,
        reason="category_spike",
        detail=(
            f"₹{amount:,.0f} on '{label}' is {deviation:.1f}σ above your "
            f"{label} average of ₹{avg:,.0f}."
            if deviation is not None
            else f"₹{amount:,.0f} on '{label}' exceeds your usual spend."
        ),
        expected_mean=avg.quantize(Decimal("0.01")),
        expected_max=cutoff.quantize(Decimal("0.01")),
        deviation_ratio=deviation,
    )


def _new_large_merchant(
    txn: CanonicalTransaction,
    category_name: str | None,
    amount: Decimal,
    history_by_merchant: dict[str, list[date]],
    window_start: date,
    floor: Decimal,
) -> AnomalyFinding | None:
    if amount < floor or not txn.merchant_normalized:
        return None
    prior_dates = history_by_merchant.get(txn.merchant_normalized.upper(), [])
    prior_outside_window = [d for d in prior_dates if d < window_start]
    if prior_outside_window:
        # We've seen this merchant before — not a first-time event.
        return None
    return AnomalyFinding(
        transaction_id=txn.id,
        transaction_date=txn.transaction_date,
        amount=amount,
        merchant=txn.merchant_normalized,
        category_id=txn.category_id,
        category_name=category_name,
        bank_name=txn.bank_name,
        reason="new_large_merchant",
        detail=(
            f"First time spending ₹{amount:,.0f} with '{txn.merchant_normalized}'."
        ),
        expected_mean=None,
        expected_max=None,
        deviation_ratio=None,
    )
