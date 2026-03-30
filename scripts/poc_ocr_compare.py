#!/usr/bin/env python3
"""POC: compare text extraction quality and optional OCR fallback on local PDFs."""

from __future__ import annotations

import argparse
import importlib
import io
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))


def _optional_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _ocr_first_page(pdf_bytes: bytes) -> tuple[str | None, str | None]:
    pdfplumber = _optional_import("pdfplumber")
    if pdfplumber is None:
        return None, "pdfplumber_not_installed"
    pytesseract = _optional_import("pytesseract")
    if pytesseract is None:
        return None, "pytesseract_not_installed"

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return None, "empty_pdf"
            img = pdf.pages[0].to_image(resolution=200).original
        text = pytesseract.image_to_string(img, lang="eng")
        return text, None
    except Exception as exc:
        return None, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--folder",
        default="/home/ankit/Documents/FY24-25-Ankit-details",
        help="Folder with PDFs",
    )
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument(
        "--password-map",
        default="",
        help="Optional JSON file: {\"filename.pdf\":\"password\"}",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        raise SystemExit(f"Folder does not exist: {folder}")

    try:
        from app.engines.parser.pdf_utils import decrypt_pdf, extract_text
    except ModuleNotFoundError as exc:
        print(
            json.dumps(
                {
                    "error": "missing_dependency",
                    "detail": str(exc),
                    "hint": "Run with backend virtualenv: backend/.venv/bin/python scripts/poc_ocr_compare.py",
                },
                indent=2,
            )
        )
        return

    password_map: dict[str, str] = {}
    if args.password_map:
        password_map = json.loads(Path(args.password_map).read_text())

    results = []
    for pdf in sorted(folder.rglob("*.pdf"))[: max(1, args.limit)]:
        try:
            password = password_map.get(pdf.name)
            decrypted = decrypt_pdf(pdf.read_bytes(), password)
            pages = extract_text(decrypted)
            machine_chars = sum(len(page or "") for page in pages)
            ocr_text, ocr_error = _ocr_first_page(decrypted)
            results.append(
                {
                    "file": str(pdf),
                    "pages": len(pages),
                    "machine_chars": machine_chars,
                    "machine_chars_page1": len(pages[0]) if pages else 0,
                    "ocr_chars_page1": len(ocr_text) if ocr_text else None,
                    "ocr_error": ocr_error,
                }
            )
        except Exception as exc:
            results.append({"file": str(pdf), "error": str(exc)})

    print(json.dumps({"files_scanned": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
