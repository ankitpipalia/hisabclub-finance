"""Merchant normalization — matches raw transaction descriptions to known merchants."""

from __future__ import annotations

import re
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant, MerchantPattern

_PATTERN_CACHE_TTL_SEC = 300.0
_pattern_cache: tuple[float, list[tuple[MerchantPattern, Merchant]]] | None = None


async def normalize_and_categorize(
    db: AsyncSession, description_raw: str
) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    """Match a raw description to a known merchant and its default category.

    Returns (merchant_id, category_id, merchant_display_name).
    """
    description_upper = description_raw.upper().strip()

    rows = await _load_patterns(db)

    for pattern_row, merchant in rows:
        matched = False

        if pattern_row.pattern_type == "exact":
            matched = description_upper == pattern_row.pattern.upper()
        elif pattern_row.pattern_type == "contains":
            matched = pattern_row.pattern.upper() in description_upper
        elif pattern_row.pattern_type == "regex":
            try:
                matched = bool(re.search(pattern_row.pattern, description_raw, re.IGNORECASE))
            except re.error:
                continue

        if matched:
            return merchant.id, merchant.default_category_id, merchant.display_name

    return None, None, None


async def _load_patterns(db: AsyncSession) -> list[tuple[MerchantPattern, Merchant]]:
    global _pattern_cache
    now = time.monotonic()
    if _pattern_cache is not None:
        cached_at, rows = _pattern_cache
        if now - cached_at <= _PATTERN_CACHE_TTL_SEC:
            return rows

    result = await db.execute(
        select(MerchantPattern, Merchant)
        .join(Merchant, MerchantPattern.merchant_id == Merchant.id)
        .order_by(MerchantPattern.priority.desc())
    )
    rows = list(result.all())
    _pattern_cache = (now, rows)
    return rows
