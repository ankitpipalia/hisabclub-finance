"""Indian amount and date parsing utilities."""

from __future__ import annotations

import re
from datetime import date

from dateutil import parser as dateutil_parser


def parse_indian_amount(text: str) -> float | None:
    """Parse an Indian-formatted amount string to float.

    Handles formats like:
    - 1,23,456.78
    - Rs. 1,23,456.78
    - INR 1,23,456.78
    - 1234.56
    - (1,234.56)  (negative in parens)
    - 1,234.56 Cr / 1,234.56 Dr
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Remove currency prefixes (including C which is ₹ in some HDFC PDFs)
    text = re.sub(r"(?:Rs\.?|INR|₹)\s*", "", text, flags=re.IGNORECASE)
    # Remove standalone C prefix (HDFC Swiggy card uses C for ₹)
    text = re.sub(r"^C\s*", "", text)

    # Check for negative in parentheses
    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1]

    # Remove commas (Indian numbering: 1,23,456.78)
    text = text.replace(",", "")

    # Extract numeric part
    match = re.search(r"([\d]+\.?\d*)", text)
    if not match:
        return None

    amount = float(match.group(1))

    if is_negative:
        amount = -amount

    return amount


def parse_indian_date(text: str) -> date | None:
    """Parse dates in common Indian statement formats.

    Handles:
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - DD/MM/YY, DD-MM-YY
    - DD MMM YYYY, DD-MMM-YYYY, DD/MMM/YYYY
    - DD MMM YY
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Try common Indian formats explicitly (DD/MM/YYYY is ambiguous for dateutil)
    patterns = [
        # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        (r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", "%d/%m/%Y"),
        # DD/MM/YY
        (r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})$", "%d/%m/%y"),
        # DD-MMM-YYYY or DD/MMM/YYYY or DD MMM YYYY
        (r"(\d{1,2})[/\-.\s]([A-Za-z]{3})[/\-.\s](\d{4})", None),
        # DD-MMM-YY or DD MMM YY
        (r"(\d{1,2})[/\-.\s]([A-Za-z]{3})[/\-.\s](\d{2})$", None),
    ]

    for pattern, fmt in patterns:
        match = re.match(pattern, text)
        if match:
            if fmt:
                normalized = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
                try:
                    from datetime import datetime

                    parsed = datetime.strptime(normalized, fmt.replace("-", "/")).date()
                    return parsed if _is_reasonable_statement_date(parsed) else None
                except ValueError:
                    continue
            else:
                # Use dateutil for month name formats (handles MMM correctly)
                try:
                    parsed = dateutil_parser.parse(text, dayfirst=True).date()
                    return parsed if _is_reasonable_statement_date(parsed) else None
                except (ValueError, TypeError):
                    continue

    # Fallback to dateutil with dayfirst=True
    try:
        parsed = dateutil_parser.parse(text, dayfirst=True).date()
        return parsed if _is_reasonable_statement_date(parsed) else None
    except (ValueError, TypeError):
        return None


def is_credit_indicator(text: str) -> bool | None:
    """Check if text indicates a credit transaction.

    Returns True for credit, False for debit, None if unclear.
    """
    text = text.strip().upper()
    if text in ("CR", "CR.", "C", "CREDIT"):
        return True
    if text in ("DR", "DR.", "D", "DEBIT"):
        return False
    return None


def _is_reasonable_statement_date(value: date) -> bool:
    today = date.today()
    min_date = date(2010, 1, 1)
    max_date = date(min(today.year + 2, 2099), 12, 31)
    return min_date <= value <= max_date
