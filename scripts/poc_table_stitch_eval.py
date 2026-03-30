#!/usr/bin/env python3
"""POC: evaluate stitched table extraction quality on local statement PDFs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--folder",
        default="/home/ankit/Documents/FY24-25-Ankit-details",
        help="Folder containing PDF statements",
    )
    parser.add_argument("--limit", type=int, default=80)
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
        from app.engines.parser.pdf_utils import (
            decrypt_pdf,
            estimate_expected_transaction_rows,
            extract_stitched_table_rows,
            extract_text,
        )
    except ModuleNotFoundError as exc:
        print(
            json.dumps(
                {
                    "error": "missing_dependency",
                    "detail": str(exc),
                    "hint": "Run with backend virtualenv: backend/.venv/bin/python scripts/poc_table_stitch_eval.py",
                },
                indent=2,
            )
        )
        return

    password_map = {}
    if args.password_map:
        password_map = json.loads(Path(args.password_map).read_text())

    pdfs = sorted(folder.rglob("*.pdf"))[: max(1, args.limit)]
    rows = []
    for pdf in pdfs:
        password = password_map.get(pdf.name)
        try:
            content = pdf.read_bytes()
            decrypted = decrypt_pdf(content, password)
            pages = extract_text(decrypted)
            stitched = extract_stitched_table_rows(decrypted)
            expected = estimate_expected_transaction_rows(decrypted, pages)
            rows.append(
                {
                    "file": str(pdf),
                    "pages": len(pages),
                    "chars": sum(len(page) for page in pages),
                    "stitched_rows": len(stitched),
                    "expected_rows": expected,
                    "sample": stitched[:3],
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "file": str(pdf),
                    "error": str(exc),
                }
            )

    output = {
        "folder": str(folder),
        "files_scanned": len(rows),
        "results": rows,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
