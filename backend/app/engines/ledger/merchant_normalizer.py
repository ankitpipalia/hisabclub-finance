"""Merchant normalization — matches raw transaction descriptions to known merchants."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant, MerchantPattern


async def normalize_and_categorize(
    db: AsyncSession, description_raw: str
) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    """Match a raw description to a known merchant and its default category.

    Returns (merchant_id, category_id, merchant_display_name).
    """
    description_upper = description_raw.upper().strip()

    # Fetch all patterns ordered by priority (highest first)
    result = await db.execute(
        select(MerchantPattern, Merchant)
        .join(Merchant, MerchantPattern.merchant_id == Merchant.id)
        .order_by(MerchantPattern.priority.desc())
    )
    rows = result.all()

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
