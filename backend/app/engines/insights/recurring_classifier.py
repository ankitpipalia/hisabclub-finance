"""Classify a detected RecurringPattern into a user-meaningful bucket.

Distinct from `recurring_detector.py` (which discovers patterns); this only
runs at API time so re-classifying after a categorization fix is free and
no schema migration is required.

Buckets:
- "rent"           — house/flat/property rent
- "utility"        — electricity / water / gas / internet / mobile
- "emi"            — loan EMI / installment
- "insurance"      — life/health/vehicle policy premium
- "subscription"   — streaming / OTT / software / gym
- "salary"         — credits with regular cadence and salary-like keywords
- "investment"     — SIP / mutual fund / PPF / NPS recurring
- "other"          — recurring pattern that doesn't match a rule above
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("rent", re.compile(r"\b(rent|landlord|property\s*rent|flat\s*rent)\b", re.IGNORECASE)),
    (
        "utility",
        re.compile(
            r"\b(electricity|bescom|tata\s*power|adani\s*electric|reliance\s*energy|"
            r"water\s*bill|bwssb|gas\s*bill|broadband|jio\s*fiber|airtel\s*xstream|"
            r"act\s*fibernet|hathway|tata\s*sky|d2h|prepaid|postpaid|mobile\s*bill|"
            r"recharge|utilit(?:y|ies))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "emi",
        re.compile(
            r"\b(emi|installment|loan\s*repayment|home\s*loan|car\s*loan|personal\s*loan|"
            r"two\s*wheeler\s*loan|education\s*loan)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "insurance",
        re.compile(
            r"\b(insurance|policy\s*premium|mediclaim|lic|hdfc\s*life|max\s*life|"
            r"icici\s*pru|term\s*plan|car\s*insurance|two\s*wheeler\s*insurance)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "subscription",
        re.compile(
            r"\b(netflix|prime\s*video|hotstar|disney|spotify|apple\s*music|"
            r"youtube\s*premium|youtube\s*music|sony\s*liv|zee5|swiggy\s*one|"
            r"zomato\s*gold|gym|cult[\s._-]?fit|fitness|google\s*one|icloud|"
            r"dropbox|microsoft\s*365|office\s*365|github|notion|substack)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "salary",
        re.compile(
            r"\b(salary|sal\s*credit|payroll|stipend|wages|consultancy\s*fee)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "investment",
        re.compile(
            r"\b(sip\b|mutual\s*fund|ppf\s*contribution|nps\s*contribution|"
            r"recurring\s*deposit|rd\b|elss|kuvera|groww|coin|zerodha|paytm\s*money)\b",
            re.IGNORECASE,
        ),
    ),
]


@dataclass(frozen=True)
class _ProbeInput:
    description: str
    category_name: str | None


def classify_recurring(description: str, category_name: str | None = None) -> str:
    """Return the classification bucket for a recurring pattern.

    Matches against the description first; falls back to category name when
    description is too generic (e.g. a stub like "Auto-debit ICICI"). Returns
    "other" when no rule fires.
    """
    haystack = " ".join(filter(None, [description or "", category_name or ""]))
    for label, pattern in _RULES:
        if pattern.search(haystack):
            return label
    return "other"


def classify_many(items: Iterable[tuple[str, str | None]]) -> list[str]:
    return [classify_recurring(desc, cat) for desc, cat in items]
