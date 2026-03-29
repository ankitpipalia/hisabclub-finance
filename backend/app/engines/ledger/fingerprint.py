"""Deterministic fingerprint utilities for statement and transaction dedup."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]+")


def _normalize_description(description: str) -> str:
    text = (description or "").upper().strip()
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def _to_paise(amount: float | Decimal) -> int:
    value = Decimal(str(amount)).copy_abs().quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(value * 100)


def build_transaction_dedupe_fingerprint(
    *,
    user_id: uuid.UUID,
    account_masked: str | None,
    transaction_date: date,
    amount: float | Decimal,
    description: str,
) -> str:
    """Builds SHA-256 over the agreed deterministic dedup key.

    Formula:
    user_id || account_masked || date_iso || abs(amount_paise) || normalize(description)[0:30]
    """
    normalized_desc = _normalize_description(description)[:30]
    raw = "|".join(
        [
            str(user_id),
            (account_masked or "").strip().upper(),
            transaction_date.isoformat(),
            str(_to_paise(amount)),
            normalized_desc,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_statement_semantic_fingerprint(
    *,
    user_id: uuid.UUID,
    institution_name: str,
    account_masked: str | None,
    period_start: date | None,
    period_end: date | None,
    opening_balance: float | Decimal | None,
) -> str | None:
    """Builds a semantic statement fingerprint for non-byte-identical duplicates.

    Returns None when mandatory semantic fields are unavailable.
    """
    if not institution_name or period_start is None or period_end is None:
        return None

    opening = ""
    if opening_balance is not None:
        opening = str(_to_paise(opening_balance))

    raw = "|".join(
        [
            str(user_id),
            institution_name.strip().upper(),
            (account_masked or "").strip().upper(),
            period_start.isoformat(),
            period_end.isoformat(),
            opening,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
