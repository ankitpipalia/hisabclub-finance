"""PDF utilities — decryption and text extraction."""

from __future__ import annotations

import io

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
