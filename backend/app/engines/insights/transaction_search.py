"""Semantic-ish transaction search.

Token-weighted ranking over the user's canonical transactions. No external
dependency (no pgvector, no Elasticsearch) — just SQL ILIKE for narrowing
plus an in-memory rerank by term-frequency × field-weight × exact-phrase
bonus. Designed for the dashboard search bar: ≤10k user transactions, ≤200ms.

Privacy: all matching happens inside Postgres + Python on the same box. No
network calls; no embedding model required.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category

_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}")

# Per-field weights applied per matched token.
_FIELD_WEIGHTS = {
    "merchant_normalized": 3.0,
    "merchant_raw": 2.0,
    "notes": 1.0,
    "bank_name": 1.0,
}

_EXACT_PHRASE_BONUS = 5.0


@dataclass(frozen=True)
class SearchHit:
    transaction_id: uuid.UUID
    transaction_date: date
    amount: Decimal
    direction: str
    merchant: str
    category_name: str | None
    bank_name: str | None
    account_masked: str | None
    score: float
    matched_terms: list[str]

    def to_dict(self) -> dict:
        return {
            "transaction_id": str(self.transaction_id),
            "transaction_date": self.transaction_date.isoformat(),
            "amount": str(self.amount),
            "direction": self.direction,
            "merchant": self.merchant,
            "category_name": self.category_name,
            "bank_name": self.bank_name,
            "account_masked": self.account_masked,
            "score": round(self.score, 3),
            "matched_terms": self.matched_terms,
        }


def _tokenize(query: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(query)]


def _score(
    txn: CanonicalTransaction,
    category_name: str | None,
    tokens: list[str],
    phrase_lower: str,
) -> tuple[float, list[str]]:
    fields = {
        "merchant_normalized": (txn.merchant_normalized or "").lower(),
        "merchant_raw": (txn.merchant_raw or "").lower(),
        "notes": (txn.notes or "").lower(),
        "bank_name": (txn.bank_name or "").lower(),
    }
    score = 0.0
    matched: list[str] = []
    for token in tokens:
        if not token:
            continue
        token_matched = False
        for field, value in fields.items():
            if token in value:
                score += _FIELD_WEIGHTS[field]
                token_matched = True
        if token_matched:
            matched.append(token)
    if phrase_lower:
        for value in fields.values():
            if phrase_lower in value:
                score += _EXACT_PHRASE_BONUS
                break
    # Tiny boost when the user's stored category name matches.
    if category_name and any(t in category_name.lower() for t in tokens):
        score += 1.5
    return score, matched


async def search_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    *,
    limit: int = 25,
    max_candidates: int = 500,
) -> list[SearchHit]:
    """Rank user's transactions by relevance to `query`.

    Returns up to `limit` hits sorted by score desc, then date desc.
    """
    tokens = _tokenize(query)
    if not tokens:
        return []
    phrase = query.strip()
    phrase_lower = phrase.lower() if phrase else ""

    # ILIKE narrowing — match if ANY token appears in any of the major fields.
    like_clauses = []
    for token in tokens:
        wild = f"%{token}%"
        like_clauses.extend(
            [
                CanonicalTransaction.merchant_normalized.ilike(wild),
                CanonicalTransaction.merchant_raw.ilike(wild),
                CanonicalTransaction.notes.ilike(wild),
                CanonicalTransaction.bank_name.ilike(wild),
            ]
        )
    statement = (
        select(CanonicalTransaction, Category.name.label("category_name"))
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(
            CanonicalTransaction.user_id == user_id,
            CanonicalTransaction.is_excluded == False,  # noqa: E712
            or_(*like_clauses),
        )
        .order_by(CanonicalTransaction.transaction_date.desc())
        .limit(max_candidates)
    )
    rows = (await db.execute(statement)).all()
    if not rows:
        return []

    hits: list[SearchHit] = []
    for txn, category_name in rows:
        score, matched = _score(txn, category_name, tokens, phrase_lower)
        if score <= 0:
            continue
        hits.append(
            SearchHit(
                transaction_id=txn.id,
                transaction_date=txn.transaction_date,
                amount=Decimal(str(txn.amount)),
                direction=txn.direction,
                merchant=txn.merchant_normalized or txn.merchant_raw or "Unknown",
                category_name=category_name,
                bank_name=txn.bank_name,
                account_masked=txn.account_masked,
                score=score,
                matched_terms=list(dict.fromkeys(matched)),
            )
        )

    hits.sort(key=lambda h: (h.score, h.transaction_date), reverse=True)
    return hits[:limit]
