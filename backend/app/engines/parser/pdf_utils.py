"""PDF utilities — decryption and text extraction."""

from __future__ import annotations

import io
import re

import pdfplumber
import pikepdf


def decrypt_pdf(pdf_content: bytes, password: str | None = None) -> bytes:
    """Decrypt a password-protected PDF. Returns decrypted bytes.

    If no password is provided, tries opening without one.
    If the PDF is not encrypted, returns the content as-is.
    """
    try:
        # Try opening without password first
        pdf = pikepdf.open(io.BytesIO(pdf_content))
        # If it opens, save to bytes (strips encryption metadata)
        buf = io.BytesIO()
        pdf.save(buf)
        pdf.close()
        return buf.getvalue()
    except pikepdf.PasswordError:
        pass

    if not password:
        raise ValueError(
            "This PDF is password-protected. Please provide the password."
        )

    try:
        pdf = pikepdf.open(io.BytesIO(pdf_content), password=password)
        buf = io.BytesIO()
        pdf.save(buf)
        pdf.close()
        return buf.getvalue()
    except pikepdf.PasswordError:
        raise ValueError("Incorrect password for this PDF.")


def extract_text(pdf_bytes: bytes) -> list[str]:
    """Extract text from each page of a PDF using pdfplumber.

    Returns a list of strings, one per page.
    """
    pages: list[str] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
            else:
                # Try extracting with different settings for difficult layouts
                text = page.extract_text(
                    x_tolerance=3,
                    y_tolerance=3,
                )
                pages.append(text or "")

    return pages


def extract_tables(pdf_bytes: bytes) -> list[list[list[str | None]]]:
    """Extract tables from a PDF using pdfplumber's table detection.

    Returns a list of tables, where each table is a list of rows,
    and each row is a list of cell values.
    """
    tables: list[list[list[str | None]]] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            if page_tables:
                tables.extend(page_tables)

    return tables


def extract_stitched_table_rows(pdf_bytes: bytes, *, max_rows: int = 6000) -> list[str]:
    """Extract table rows and stitch cross-page continuations.

    Strategy:
    - preserve row order across pages
    - drop repeated header rows seen on page breaks
    - return pipe-delimited rows suitable for deterministic/table-LLM paths
    """
    rows: list[str] = []
    seen_header_lines: set[str] = set()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables() or []
            for table in page_tables:
                for raw_row in table:
                    cleaned_cells = [_clean_table_cell(cell) for cell in raw_row]
                    # Keep non-empty rows only.
                    cleaned_cells = [cell for cell in cleaned_cells if cell]
                    if not cleaned_cells:
                        continue
                    line = " | ".join(cleaned_cells)
                    if _is_table_header_line(line):
                        if line in seen_header_lines:
                            continue
                        seen_header_lines.add(line)
                    rows.append(line)
                    if len(rows) >= max_rows:
                        return rows
    return rows


_DATE_RE = re.compile(
    r"\b(?:\d{2}[/-]\d{2}[/-]\d{2,4}|\d{2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"
)
_AMOUNT_RE = re.compile(r"\b(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{2})\b")


def estimate_expected_transaction_rows(
    pdf_bytes: bytes,
    pages: list[str] | None = None,
) -> int | None:
    """Estimate expected transaction rows using table-first + line heuristics.

    The estimate is used for yield-rate monitoring, not financial posting.
    """
    table_hits = 0
    try:
        for table in extract_tables(pdf_bytes):
            for row in table:
                row_text = " ".join(cell or "" for cell in row)
                if _looks_like_transaction_row(row_text):
                    table_hits += 1
    except Exception:
        table_hits = 0

    if pages is None:
        pages = extract_text(pdf_bytes)
    line_hits = 0
    for page in pages:
        for line in page.splitlines():
            if _looks_like_transaction_row(line):
                line_hits += 1

    estimate = max(table_hits, line_hits)
    return estimate or None


def _looks_like_transaction_row(text: str) -> bool:
    normalized = " ".join((text or "").split())
    if len(normalized) < 8:
        return False
    if not _DATE_RE.search(normalized):
        return False
    amount_count = len(_AMOUNT_RE.findall(normalized))
    return amount_count >= 1


def _clean_table_cell(cell: str | None) -> str:
    if cell is None:
        return ""
    return " ".join(str(cell).replace("\n", " ").split())


def _is_table_header_line(text: str) -> bool:
    upper = text.upper()
    header_tokens = ("DATE", "DESCRIPTION", "PARTICULARS", "DEBIT", "CREDIT", "BALANCE")
    return sum(1 for token in header_tokens if token in upper) >= 2
