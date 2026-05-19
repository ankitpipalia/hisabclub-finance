from __future__ import annotations

import re

from app.engines.parser.amount_utils import parse_indian_amount

# Per-line patterns: TAN + section + credit + TDS in a row.
# 26AS Part-A rows typically look like:
#   "AAAAA1234B  ACME PVT LTD  192  1500000  150000"
# but PDF extraction yields fragmented text. We use two regex passes:
#   1. Anchor a TAN to find the line.
#   2. Scan the surrounding 200 chars for section + amounts.
_TAN_RE = re.compile(r"\b([A-Z]{4}\d{5}[A-Z])\b")
_SECTION_RE = re.compile(r"\b(192[A-Z]?|193|194[A-Z]?|195|196[A-Z]?|206[A-Z]{2})\b")
_AMOUNT_RE = re.compile(r"\b([0-9](?:[0-9,])*(?:\.\d{1,2})?)\b")
# Challan rows for Part-C (self-paid taxes).
_CHALLAN_BLOCK_RE = re.compile(
    r"(?:challan|bsr)\s*[:#]?\s*(\d{7,})", re.IGNORECASE
)


def _extract_line_items(text: str) -> list[dict]:
    lines: list[dict] = []
    seen: set[tuple] = set()
    for tan_match in _TAN_RE.finditer(text):
        tan = tan_match.group(1).upper()
        window_start = max(0, tan_match.start() - 50)
        window_end = min(len(text), tan_match.end() + 200)
        window = text[window_start:window_end]
        section_match = _SECTION_RE.search(window)
        section = section_match.group(1).upper() if section_match else None
        amounts = [
            parse_indian_amount(m.group(1))
            for m in _AMOUNT_RE.finditer(window)
            if "." in m.group(1) or len(m.group(1).replace(",", "")) >= 3
        ]
        amounts = [a for a in amounts if a is not None and a > 0]
        # In Part-A rows the largest amount is typically the gross credit; the
        # second-largest is the TDS. This is brittle on noisy OCR, but it gives
        # the reconciler a usable signal that aggregate-only didn't have.
        if not amounts:
            continue
        amount_credit = max(amounts)
        rest = sorted([a for a in amounts if a < amount_credit], reverse=True)
        amount_tds = rest[0] if rest else None
        key = (tan, section, round(amount_credit, 2))
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            {
                "part": "A" if section else "B",
                "deductor_tan": tan,
                "section": section,
                "amount_credit": round(amount_credit, 2),
                "amount_tds": round(amount_tds, 2) if amount_tds is not None else None,
                "raw_match": window.strip()[:160],
            }
        )

    # Part-C self-paid challan rows (heuristic).
    for challan_match in _CHALLAN_BLOCK_RE.finditer(text):
        window = text[challan_match.start():challan_match.start() + 200]
        amts = [
            parse_indian_amount(m.group(1))
            for m in _AMOUNT_RE.finditer(window)
            if "." in m.group(1) or len(m.group(1).replace(",", "")) >= 4
        ]
        amts = [a for a in amts if a is not None and a > 100]
        if not amts:
            continue
        lines.append(
            {
                "part": "C",
                "deductor_tan": None,
                "section": "self_paid_challan",
                "amount_credit": round(max(amts), 2),
                "amount_tds": None,
                "raw_match": window.strip()[:160],
            }
        )
    return lines


def parse_form_26as_document(text: str, *, source_filename: str | None = None) -> dict:
    tds_total = _sum_amounts(
        text,
        (
            r"(?:tax deducted|tds deposited|total tax deducted)"
            r"[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
        ),
    )
    tax_paid_total = _sum_amounts(
        text,
        (
            r"(?:advance tax|self assessment tax|challan amount|tax paid)"
            r"[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
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
    lines = _extract_line_items(text)
    return {
        "document_type": "form_26as",
        "source_filename": source_filename,
        "tds_total": round(tds_total, 2),
        "tax_paid_total": round(tax_paid_total, 2),
        "refund_total": round(refund_total, 2),
        "sft_total": round(sft_total, 2),
        "self_paid_total": round(tax_paid_total, 2),
        "lines": lines,
    }


def _sum_amounts(text: str, patterns: tuple[str, ...]) -> float:
    total = 0.0
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = parse_indian_amount(match.group(1))
            if parsed is not None:
                total += abs(parsed)
    return total

