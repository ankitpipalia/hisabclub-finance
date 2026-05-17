"""Tax-planning helper — aggregates YTD spend / contribution per deduction
section against statutory limits.

Category-name-based rule mapping (no schema change). The mapping intentionally
errs on the side of including too much, since the goal is "show the user
something useful right now" not "produce a filing-grade ITR draft". Users
re-categorize transactions on the regular flow; the next call to this
endpoint reflects their corrections.

Indian FY runs April → March. For FY24-25, FY label is "FY24-25".
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category

# (section, label, regex, limit_inr, counts_credits)
# `counts_credits` is True for sections like 80TTA where the income we're
# tracking is *receipts*; everywhere else we sum debits.
_RULES: list[tuple[str, str, re.Pattern[str], Decimal, bool]] = [
    (
        "80C",
        "Section 80C — investments / life insurance / EPF / PPF / ELSS",
        re.compile(
            r"\b(ppf|elss|nps\b|nps tier 1|life insurance|sukanya|epf|vpf|home loan principal|5-?year tax saving fd|tax saver fd|nsc)\b",
            re.IGNORECASE,
        ),
        Decimal("150000"),
        False,
    ),
    (
        "80D",
        "Section 80D — health insurance premiums",
        re.compile(
            r"\b(health insurance|medical insurance|mediclaim|preventive health)\b",
            re.IGNORECASE,
        ),
        Decimal("25000"),
        False,
    ),
    (
        "80D-parents",
        "Section 80D (parents) — additional health insurance for parents",
        re.compile(
            r"\b(parents?\s*(health|medical)\s*insurance|parents?\s*mediclaim)\b",
            re.IGNORECASE,
        ),
        Decimal("50000"),
        False,
    ),
    (
        "80E",
        "Section 80E — education loan interest",
        re.compile(r"\b(education loan interest|student loan interest)\b", re.IGNORECASE),
        Decimal("0"),  # no statutory cap
        False,
    ),
    (
        "80G",
        "Section 80G — donations to approved entities",
        re.compile(r"\b(donation|charity|relief fund)\b", re.IGNORECASE),
        Decimal("0"),
        False,
    ),
    (
        "24b",
        "Section 24(b) — home loan interest on self-occupied property",
        re.compile(r"\b(home loan interest|housing loan interest)\b", re.IGNORECASE),
        Decimal("200000"),
        False,
    ),
    (
        "80TTA",
        "Section 80TTA — interest from savings accounts (up to ₹10,000)",
        re.compile(r"\b(savings interest|interest credit|interest paid)\b", re.IGNORECASE),
        Decimal("10000"),
        True,
    ),
]


@dataclass
class TaxPlanningSection:
    section: str
    label: str
    ytd_amount: Decimal
    limit: Decimal
    remaining: Decimal | None
    progress_pct: float | None  # null when no statutory cap


def parse_financial_year(value: str) -> tuple[date, date]:
    """Parse 'FY24-25' or '2024-25' into (start, end) where start=Apr-1, end=Mar-31."""
    match = re.match(r"(?:FY)?\s*(\d{2,4})\s*[-/]\s*(\d{2,4})", value.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid FY format: {value!r}")
    raw_a, raw_b = match.group(1), match.group(2)
    start_year = int(raw_a) if len(raw_a) == 4 else 2000 + int(raw_a)
    end_year = int(raw_b) if len(raw_b) == 4 else 2000 + int(raw_b)
    if end_year < start_year:
        end_year += 100
    return date(start_year, 4, 1), date(end_year, 3, 31)


async def compute_tax_planning_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    financial_year: str,
) -> list[TaxPlanningSection]:
    fy_start, fy_end = parse_financial_year(financial_year)

    rows = (
        await db.execute(
            select(
                CanonicalTransaction.amount,
                CanonicalTransaction.direction,
                CanonicalTransaction.merchant_normalized,
                CanonicalTransaction.merchant_raw,
                Category.name.label("category_name"),
            )
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.is_excluded == False,  # noqa: E712
                CanonicalTransaction.transaction_date >= fy_start,
                CanonicalTransaction.transaction_date <= fy_end,
            )
        )
    ).all()

    totals: dict[str, Decimal] = {section: Decimal("0") for section, *_ in _RULES}
    for amount, direction, merchant_normalized, merchant_raw, category_name in rows:
        searchable = " ".join(
            filter(None, [category_name or "", merchant_normalized or "", merchant_raw or ""])
        )
        for section, _label, pattern, _limit, counts_credits in _RULES:
            if not pattern.search(searchable):
                continue
            if counts_credits:
                if direction == "credit":
                    totals[section] += Decimal(str(amount))
            else:
                if direction == "debit":
                    totals[section] += Decimal(str(amount))

    summaries: list[TaxPlanningSection] = []
    for section, label, _pattern, limit, _counts_credits in _RULES:
        ytd = totals[section].quantize(Decimal("0.01"))
        if limit > 0:
            remaining = max(Decimal("0"), limit - ytd)
            progress_pct = float(min(Decimal("1"), ytd / limit)) * 100.0
        else:
            remaining = None
            progress_pct = None
        summaries.append(
            TaxPlanningSection(
                section=section,
                label=label,
                ytd_amount=ytd,
                limit=limit,
                remaining=remaining,
                progress_pct=round(progress_pct, 2) if progress_pct is not None else None,
            )
        )
    return summaries
