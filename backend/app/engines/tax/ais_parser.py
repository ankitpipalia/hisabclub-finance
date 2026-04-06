from __future__ import annotations

import re

from app.engines.parser.amount_utils import parse_indian_amount


def parse_ais_document(text: str, *, source_filename: str | None = None, document_type: str = "ais") -> dict:
    interest_total = _sum_keyword_amounts(
        text,
        ("interest", "savings interest", "deposit interest", "fd interest"),
    )
    dividend_total = _sum_keyword_amounts(text, ("dividend",))
    salary_total = _sum_keyword_amounts(text, ("salary", "salary income"))
    securities_total = _sum_keyword_amounts(
        text,
        ("mutual fund", "shares", "stocks", "securities"),
    )
    return {
        "document_type": document_type,
        "source_filename": source_filename,
        "interest_income": round(interest_total, 2),
        "dividend_income": round(dividend_total, 2),
        "salary_income": round(salary_total, 2),
        "securities_activity": round(securities_total, 2),
    }


def _sum_keyword_amounts(text: str, keywords: tuple[str, ...]) -> float:
    total = 0.0
    for keyword in keywords:
        for match in re.finditer(
            rf"{re.escape(keyword)}[^0-9]{{0,30}}([0-9][0-9,]*(?:\.\d{{1,2}})?)",
            text,
            flags=re.IGNORECASE,
        ):
            parsed = parse_indian_amount(match.group(1))
            if parsed is not None:
                total += abs(parsed)
    return total

