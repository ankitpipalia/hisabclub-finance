from __future__ import annotations

import re
from datetime import date

from app.engines.parser.amount_utils import parse_indian_amount, parse_indian_date

_AMOUNT_CAPTURE = r"([0-9][0-9,]*(?:\.\d{1,2})?)"


def extract_tax_document_metadata(
    *,
    doc_type: str,
    text: str,
    source_filename: str | None = None,
) -> dict:
    normalized_type = (doc_type or "").strip().lower()
    safe_text = text or ""
    metadata: dict[str, object] = {
        "doc_type": normalized_type,
        "source_filename": source_filename,
        "financial_year": _extract_financial_year(safe_text),
    }

    if normalized_type == "interest_certificate":
        metadata.update(_parse_interest_certificate(safe_text))
    elif normalized_type == "fd_report":
        metadata.update(_parse_fd_report(safe_text))
    elif normalized_type == "tax_challan":
        metadata.update(_parse_tax_challan(safe_text))
    elif normalized_type == "ppf_statement":
        metadata.update(_parse_ppf_statement(safe_text))
    elif normalized_type == "tax_form":
        metadata.update(_parse_tax_form(safe_text))

    # Normalize floating-point values for stable API responses.
    for key, value in list(metadata.items()):
        if isinstance(value, float):
            metadata[key] = round(value, 2)
    return metadata


def _parse_interest_certificate(text: str) -> dict:
    interest_amount = _find_first_amount(
        text,
        (
            rf"total\s+interest[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"interest\s+(?:paid|credited|accrued|income|amount)[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"interest[^0-9]{{0,10}}{_AMOUNT_CAPTURE}",
        ),
    )
    tds_amount = _find_first_amount(
        text,
        (
            rf"total\s+tds[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"tds\s+(?:deducted|amount|u/s)?[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
        ),
    )
    return {
        "interest_amount": interest_amount or 0.0,
        "tds_amount": tds_amount or 0.0,
    }


def _parse_fd_report(text: str) -> dict:
    principal_values = _extract_keyword_amounts(
        text,
        (
            "principal amount",
            "deposit amount",
            "amount invested",
            "face value",
        ),
    )
    interest_values = _extract_keyword_amounts(
        text,
        (
            "interest amount",
            "interest accrued",
            "interest payable",
        ),
    )
    maturity_values = _extract_keyword_amounts(
        text,
        (
            "maturity amount",
            "maturity value",
        ),
    )
    fd_mentions = len(re.findall(r"\b(?:fd|fixed deposit)\b", text, flags=re.IGNORECASE))
    fd_no_mentions = len(re.findall(r"\b(?:fd\s*no|deposit\s*no)\b", text, flags=re.IGNORECASE))
    fd_count = max(fd_mentions, fd_no_mentions)
    return {
        "fd_count": fd_count,
        "principal_total": float(sum(principal_values)),
        "interest_total": float(sum(interest_values)),
        "maturity_total": float(sum(maturity_values)),
    }


def _parse_tax_challan(text: str) -> dict:
    paid_amount = _find_first_amount(
        text,
        (
            rf"(?:challan|tax)\s+(?:amount|paid|payment)[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"total\s+(?:amount\s+paid|tax\s+paid)[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"amount\s+paid[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
        ),
    )
    challan_date = _extract_date_for_keywords(
        text,
        (
            "challan date",
            "date of deposit",
            "payment date",
            "date",
        ),
    )
    cin = _extract_first_group(
        text,
        (
            r"\bCIN(?:\s*No\.?|:)?\s*([A-Z0-9/-]{8,})",
            r"\bChallan\s+Identification\s+Number(?:\s*:?)*\s*([A-Z0-9/-]{8,})",
        ),
    )
    bsr_code = _extract_first_group(text, (r"\bBSR\s*Code(?:\s*:?)*\s*([0-9]{7})",))
    challan_serial = _extract_first_group(
        text,
        (
            r"\bChallan\s*(?:No\.?|Serial\s*No\.?)(?:\s*:?)*\s*([A-Z0-9-]{3,})",
            r"\bSerial\s*No\.?(?:\s*:?)*\s*([A-Z0-9-]{3,})",
        ),
    )
    return {
        "tax_paid_amount": paid_amount or 0.0,
        "challan_date": challan_date.isoformat() if challan_date else None,
        "cin": cin,
        "bsr_code": bsr_code,
        "challan_serial_no": challan_serial,
    }


def _parse_ppf_statement(text: str) -> dict:
    opening_balance = _find_first_amount(
        text,
        (rf"opening\s+balance[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",),
    )
    closing_balance = _find_first_amount(
        text,
        (
            rf"closing\s+balance[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"balance\s+as\s+on[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
        ),
    )
    interest_amount = _find_first_amount(
        text,
        (
            rf"interest\s+(?:credited|deposited|amount)[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"interest[^0-9]{{0,12}}{_AMOUNT_CAPTURE}",
        ),
    )
    contribution_amount = _find_first_amount(
        text,
        (
            rf"(?:subscription|deposit|contribution)[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"total\s+deposits?[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
        ),
    )
    account_raw = _extract_first_group(
        text,
        (
            r"\bPPF\s*(?:A\/C|Account)?\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([0-9Xx*]{6,20})",
            r"\bAccount\s*(?:No\.?|Number|#)\s*[:\-]?\s*([0-9Xx*]{6,20})",
        ),
    )
    return {
        "ppf_account_masked": _mask_account(account_raw),
        "opening_balance": opening_balance or 0.0,
        "closing_balance": closing_balance or 0.0,
        "interest_amount": interest_amount or 0.0,
        "contribution_amount": contribution_amount or 0.0,
    }


def _parse_tax_form(text: str) -> dict:
    gross_salary = _find_first_amount(
        text,
        (
            rf"gross\s+salary[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"salary[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
        ),
    )
    tds_amount = _find_first_amount(
        text,
        (
            rf"tax\s+deducted\s+at\s+source[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            rf"tds[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
        ),
    )
    return {
        "gross_salary": gross_salary or 0.0,
        "tds_amount": tds_amount or 0.0,
    }


def _find_first_amount(text: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        parsed = parse_indian_amount(match.group(1))
        if parsed is not None:
            return abs(parsed)
    return None


def _extract_keyword_amounts(text: str, keywords: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for keyword in keywords:
        for match in re.finditer(
            rf"{re.escape(keyword)}[^0-9]{{0,25}}{_AMOUNT_CAPTURE}",
            text,
            flags=re.IGNORECASE,
        ):
            parsed = parse_indian_amount(match.group(1))
            if parsed is not None:
                values.append(abs(parsed))
    return values


def _extract_first_group(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_date_for_keywords(text: str, keywords: tuple[str, ...]) -> date | None:
    for keyword in keywords:
        match = re.search(
            rf"{re.escape(keyword)}[^0-9A-Za-z]{{0,8}}"
            r"([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|"
            r"[0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        parsed = parse_indian_date(match.group(1))
        if parsed is not None:
            return parsed
    return None


def _extract_financial_year(text: str) -> str | None:
    match = re.search(
        r"\b(?:FY|F\.Y\.|Financial Year)\s*[:\-]?\s*([0-9]{4}\s*[-/]\s*[0-9]{2,4})\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).replace(" ", "")
    if "/" in value:
        value = value.replace("/", "-")
    return value


def _mask_account(value: str | None) -> str | None:
    if not value:
        return None
    compact = value.replace(" ", "")
    if len(compact) <= 4:
        return compact
    prefix = "X" * max(0, len(compact) - 4)
    return f"{prefix}{compact[-4:]}"
