from __future__ import annotations

import re

from app.engines.intake.tax_document_parser import extract_tax_document_metadata
from app.engines.parser.amount_utils import parse_indian_amount

_HEAD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "gross_salary",
        re.compile(
            r"(?:Gross\s*Salary|Salary\s*as\s*per\s*provisions|"
            r"Total\s*Income\s*from\s*Salary)\s*[:\-]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
            re.IGNORECASE,
        ),
    ),
    (
        "tds",
        re.compile(
            r"(?:Total\s*Tax\s*Deducted|TDS|Tax\s*Deducted\s*at\s*Source)"
            r"\s*[:\-]?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
            re.IGNORECASE,
        ),
    ),
    (
        "deduction_80c",
        re.compile(r"80C[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE),
    ),
    (
        "deduction_80d",
        re.compile(r"80D[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE),
    ),
    (
        "deduction_80ccd_1b",
        re.compile(r"80CCD\(?1B\)?[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE),
    ),
    (
        "house_rent_allowance",
        re.compile(r"HRA[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE),
    ),
    (
        "standard_deduction",
        re.compile(
            r"Standard\s*Deduction[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
            re.IGNORECASE,
        ),
    ),
]


def _extract_line_items(text: str, employer_name: str | None) -> list[dict]:
    """Pull one line per `head` from the Form-16 body.

    Each line is a dict matching the `Form16Item` schema (head, amount,
    employer_name, raw_row). The promoter idempotently inserts these into
    `form16_items` keyed on (user_id, fy, employer_tan, head).
    """
    lines: list[dict] = []
    seen_heads: set[str] = set()
    for head, pattern in _HEAD_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parsed = parse_indian_amount(match.group(1))
        if parsed is None or parsed <= 0:
            continue
        if head in seen_heads:
            continue  # take the first match per head; subsequent matches are noise
        seen_heads.add(head)
        lines.append(
            {
                "head": head,
                "amount": round(abs(parsed), 2),
                "employer_name": employer_name,
                "raw_match": match.group(0),
            }
        )
    return lines


_EMPLOYER_TAN_RE = re.compile(
    r"(?:TAN\s*of\s*(?:the\s*)?(?:Employer|Deductor)|Employer\s*TAN)\s*[:\-]?\s*([A-Z]{4}\d{5}[A-Z])",
    re.IGNORECASE,
)


def parse_form16_document(text: str, *, source_filename: str | None = None) -> dict:
    metadata = extract_tax_document_metadata(
        doc_type="tax_form",
        text=text,
        source_filename=source_filename,
    )
    employer_name = None
    employer_match = re.search(
        r"(?:Employer|Deductor)\s*Name\s*[:\-]?\s*([A-Z0-9 &.,()-]{3,120})",
        text,
        flags=re.IGNORECASE,
    )
    if employer_match:
        employer_name = employer_match.group(1).strip()

    employer_tan = None
    tan_match = _EMPLOYER_TAN_RE.search(text)
    if tan_match:
        employer_tan = tan_match.group(1).upper()

    # Old aggregate "deductions_claimed" — kept for backwards compatibility.
    deductions = 0.0
    for match in re.finditer(
        r"(?:80C|80D|80CCD|HRA|Deduction)[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
        text,
        flags=re.IGNORECASE,
    ):
        parsed = parse_indian_amount(match.group(1))
        if parsed is not None:
            deductions += abs(parsed)

    lines = _extract_line_items(text, employer_name)

    metadata.update(
        {
            "document_type": "form_16",
            "employer_name": employer_name,
            "employer_tan": employer_tan,
            "deductions_claimed": round(deductions, 2),
            "lines": lines,
        }
    )
    return metadata

