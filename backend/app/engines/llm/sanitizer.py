"""Sanitizer — strips PII before sending text to LLM."""

from __future__ import annotations

import re


def sanitize_for_llm(text: str) -> str:
    """Strip PII from text before sending to an LLM.

    Replaces:
    - Card/account numbers (16-digit, 10-18 digit sequences)
    - Names after common patterns (Name:, Dear, Mr., Mrs., Ms.)
    - Email addresses
    - Phone numbers (Indian 10-digit with optional +91 / 0 prefix)
    - PAN numbers (ABCDE1234F)
    - Aadhaar numbers (1234 5678 9012)
    - OTPs (entire lines mentioning OTP)
    """
    sanitized = text

    # Remove entire lines containing OTP
    sanitized = re.sub(
        r"(?i)^.*\bOTP\b.*$", "[OTP_LINE_REMOVED]", sanitized, flags=re.MULTILINE
    )

    # Aadhaar: 12 digits in groups of 4 (with spaces/dashes)
    sanitized = re.sub(
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "XXXX XXXX XXXX", sanitized
    )

    # PAN: 5 letters + 4 digits + 1 letter
    sanitized = re.sub(r"\b[A-Z]{5}\d{4}[A-Z]\b", "XXXX_PAN", sanitized)

    # Card/account numbers: 13-19 digits (with optional spaces/dashes)
    sanitized = re.sub(
        r"\b(?:\d[\s-]?){13,19}\b",
        "XXXX-XXXX-XXXX-XXXX",
        sanitized,
    )

    # Account numbers: 9-18 digit sequences
    sanitized = re.sub(r"\b\d{9,18}\b", "XXXX_ACCT", sanitized)

    # Email addresses
    sanitized = re.sub(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "XXXX@XXXX.XXX",
        sanitized,
    )

    # Indian phone numbers: +91, 0, or bare 10-digit
    sanitized = re.sub(
        r"(?:\+91[\s-]?|0)?[6-9]\d{9}\b", "XXXX_PHONE", sanitized
    )

    # Names after "Name:", "Dear", "Mr.", "Mrs.", "Ms."
    sanitized = re.sub(
        r"(?i)(?:name\s*:\s*|dear\s+|mr\.?\s+|mrs\.?\s+|ms\.?\s+)[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,3}",
        lambda m: m.group(0).split()[0] + " XXXX_NAME",
        sanitized,
    )

    return sanitized
