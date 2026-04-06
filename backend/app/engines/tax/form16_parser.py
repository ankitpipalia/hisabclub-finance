from __future__ import annotations

import re

from app.engines.intake.tax_document_parser import extract_tax_document_metadata
from app.engines.parser.amount_utils import parse_indian_amount


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

    deductions = 0.0
    for match in re.finditer(
        r"(?:80C|80D|80CCD|HRA|Deduction)[^0-9]{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
        text,
        flags=re.IGNORECASE,
    ):
        parsed = parse_indian_amount(match.group(1))
        if parsed is not None:
            deductions += abs(parsed)

    metadata.update(
        {
            "document_type": "form_16",
            "employer_name": employer_name,
            "deductions_claimed": round(deductions, 2),
        }
    )
    return metadata

