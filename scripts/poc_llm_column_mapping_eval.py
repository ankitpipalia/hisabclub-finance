#!/usr/bin/env python3
"""POC: evaluate tier-2 LLM column-mapping extraction on local PDFs."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

async def run_eval(folder: Path, limit: int, password_map: dict[str, str]) -> dict:
    from app.config import settings
    from app.engines.llm.client import LLMClient
    from app.engines.llm.parse_fallback import llm_parse_statement
    from app.engines.parser.pdf_utils import decrypt_pdf, extract_stitched_table_rows, extract_text

    client = LLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    pdfs = sorted(folder.rglob("*.pdf"))[: max(1, limit)]
    results = []
    for pdf in pdfs:
        password = password_map.get(pdf.name)
        try:
            content = pdf.read_bytes()
            decrypted = decrypt_pdf(content, password)
            pages = extract_text(decrypted)
            table_rows = extract_stitched_table_rows(decrypted)
            parsed = await llm_parse_statement(
                client=client,
                page_text="\n".join(pages),
                table_rows=table_rows,
                bank_hint=None,
                account_type_hint="auto",
                model=settings.llm_model,
            )
            results.append(
                {
                    "file": str(pdf),
                    "pages": len(pages),
                    "table_rows": len(table_rows),
                    "parsed": parsed is not None,
                    "parser_id": parsed.parser_id if parsed else None,
                    "transaction_count": len(parsed.transactions) if parsed else 0,
                }
            )
        except Exception as exc:
            results.append({"file": str(pdf), "error": str(exc)})

    return {"files_scanned": len(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--folder",
        default="/home/ankit/Documents/FY24-25-Ankit-details",
        help="Folder containing PDFs",
    )
    parser.add_argument("--limit", type=int, default=20)
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
        from app.config import settings as _settings  # noqa: F401
    except ModuleNotFoundError as exc:
        print(
            json.dumps(
                {
                    "error": "missing_dependency",
                    "detail": str(exc),
                    "hint": "Run with backend virtualenv: backend/.venv/bin/python scripts/poc_llm_column_mapping_eval.py",
                },
                indent=2,
            )
        )
        return

    password_map: dict[str, str] = {}
    if args.password_map:
        password_map = json.loads(Path(args.password_map).read_text())

    output = asyncio.run(run_eval(folder, args.limit, password_map))
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
