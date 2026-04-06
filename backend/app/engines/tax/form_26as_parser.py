from __future__ import annotations

import re

from app.engines.parser.amount_utils import parse_indian_amount


def parse_form_26as_document(text: str, *, source_filename: str | None = None) -> dict:
    tds_total = _sum_amounts(
        text,
        (
            r"(?:tax deducted|tds deposited|total tax deducted)[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
        ),
    )
    tax_paid_total = _sum_amounts(
        text,
        (
            r"(?:advance tax|self assessment tax|challan amount|tax paid)[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
        ),
    )
    refund_total = _sum_amounts(
        text,
        (
            r"(?:refund paid|refund amount)[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
        ),
    )
    sft_total = _sum_amounts(
        text,
        (
            r"(?:specified financial transaction|sft)[^0-9]{0,30}([0-9][0-9,]*(?:\.\d{1,2})?)",
        ),
    )
    return {
        "document_type": "form_26as",
        "source_filename": source_filename,
        "tds_total": round(tds_total, 2),
        "tax_paid_total": round(tax_paid_total, 2),
        "refund_total": round(refund_total, 2),
        "sft_total": round(sft_total, 2),
    }


def _sum_amounts(text: str, patterns: tuple[str, ...]) -> float:
    total = 0.0
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = parse_indian_amount(match.group(1))
            if parsed is not None:
                total += abs(parsed)
    return total

