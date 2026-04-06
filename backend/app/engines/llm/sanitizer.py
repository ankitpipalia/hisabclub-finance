"""Sanitizer — strips PII before sending text to LLM."""

from __future__ import annotations

import re

_REFERENCE_CONTEXT_RE = re.compile(
    r"(?i)\b(?:upi|utr|rrn|imps|neft|rtgs|txn|txnid|ref|reference|trace|order|vpa)\b"
)
_ACCOUNT_CONTEXT_RE = re.compile(
    r"(?i)\b(?:account|a/c|acct|acc(?:ount)?\s*no|card|card\s*no|ending|masked)\b"
)


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
    sanitized = re.sub(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b", "XXXX XXXX XXXX", sanitized)

    # PAN: 5 letters + 4 digits + 1 letter
    sanitized = re.sub(r"\b[A-Z]{5}\d{4}[A-Z]\b", "XXXX_PAN", sanitized)

    # Mask account/card numbers, but preserve transaction references such as
    # UPI/UTR/IMPS/NEFT IDs that are required for reconciliation.
    sanitized = re.sub(
        r"\b(?:\d[\s-]?){9,19}\b",
        _mask_sensitive_numeric_id,
        sanitized,
    )

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


def _mask_sensitive_numeric_id(match: re.Match[str]) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 9:
        return raw

    source = match.string
    start = max(0, match.start() - 18)
    end = min(len(source), match.end() + 18)
    window = source[start:end]

    if _REFERENCE_CONTEXT_RE.search(window):
        return raw

    if len(digits) >= 13:
        return "XXXX-XXXX-XXXX-XXXX"

    if _ACCOUNT_CONTEXT_RE.search(window):
        return "XXXX_ACCT"

    return raw
