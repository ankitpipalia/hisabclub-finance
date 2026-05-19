from __future__ import annotations

import re

from app.engines.parser.amount_utils import parse_indian_amount

# AIS rows follow the pattern:
#   <Information Code>  <Information Source>  <Information Description>  <Value (INR)>
# PDF-extracted text loses the column alignment; we anchor on category
# keywords and capture the nearest amount.

_CATEGORY_KEYWORDS = {
    "salary": ("salary received", "salary income", "salary"),
    "interest": (
        "interest from savings bank",
        "interest from deposit",
        "interest from fd",
        "savings interest",
        "deposit interest",
        "fd interest",
        "interest",
    ),
    "dividend": ("dividend received", "dividend"),
    "securities_sold": (
        "sale of securities",
        "sale of shares",
        "sale of mutual fund",
        "securities sold",
    ),
    "rental": ("rent received", "rental income"),
    "tds": ("tds on", "tax deducted at source"),
}


def _amount_re(keyword: str) -> re.Pattern[str]:
    return re.compile(
        rf"{re.escape(keyword)}[^0-9]{{0,40}}([0-9](?:[0-9,])*(?:\.\d{{1,2}})?)",
        re.IGNORECASE,
    )


def _extract_line_items(text: str) -> list[dict]:
    lines: list[dict] = []
    seen: set[tuple] = set()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            for match in _amount_re(keyword).finditer(text):
                parsed = parse_indian_amount(match.group(1))
                if parsed is None or parsed <= 0:
                    continue
                window_start = max(0, match.start() - 80)
                window_end = min(len(text), match.end() + 40)
                raw = text[window_start:window_end].strip()
                key = (category, round(parsed, 2), raw[:60])
                if key in seen:
                    continue
                seen.add(key)
                lines.append(
                    {
                        "category": category,
                        "sub_category": keyword,
                        "amount": round(parsed, 2),
                        "info_source": _guess_info_source(raw),
                        "raw_match": raw[:200],
                    }
                )
    return lines


_INFO_SOURCE_HINTS = (
    r"HDFC\s*BANK",
    r"ICICI\s*BANK",
    r"AXIS\s*BANK",
    r"SBI",
    r"KOTAK",
    r"YES\s*BANK",
    r"PNB",
    r"CDSL",
    r"NSDL",
)


def _guess_info_source(window: str) -> str | None:
    for hint in _INFO_SOURCE_HINTS:
        if re.search(hint, window, re.IGNORECASE):
            return re.search(hint, window, re.IGNORECASE).group(0).strip()
    return None


def parse_ais_document(
    text: str,
    *,
    source_filename: str | None = None,
    document_type: str = "ais",
) -> dict:
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
    lines = _extract_line_items(text)
    return {
        "document_type": document_type,
        "source_filename": source_filename,
        "interest_income": round(interest_total, 2),
        "dividend_income": round(dividend_total, 2),
        "salary_income": round(salary_total, 2),
        "securities_activity": round(securities_total, 2),
        # Aliases the wire-up layer also reads.
        "interest": round(interest_total, 2),
        "dividend": round(dividend_total, 2),
        "salary": round(salary_total, 2),
        "securities_sold": round(securities_total, 2),
        "lines": lines,
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

