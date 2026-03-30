from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import date

from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_factory
from app.engines.insights.tax_compliance import build_tax_compliance_report
from app.engines.intake.folder_importer import import_folder
from app.models.canonical_transaction import CanonicalTransaction
from app.models.document_artifact import DocumentArtifact
from app.models.statement import Statement
from app.security.tenant_context import apply_rls_db_role, set_request_user_context


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a local folder for an existing user.")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--parse-supported", action="store_true")
    parser.add_argument("--password-map-json", default="")
    return parser.parse_args()


async def _run(parsed: argparse.Namespace) -> None:
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)

    password_map: dict[str, str] | None = None
    if parsed.password_map_json.strip():
        loaded = json.loads(parsed.password_map_json)
        if isinstance(loaded, dict):
            password_map = {str(k): str(v) for k, v in loaded.items() if str(v).strip()}

    user_id = uuid.UUID(parsed.user_id)

    async with async_session_factory() as db:
        if settings.db_set_role_on_connect:
            await apply_rls_db_role(db, role_name=settings.db_rls_role)
        await set_request_user_context(db, user_id=user_id)

        result = await import_folder(
            db=db,
            user_id=user_id,
            folder_path=parsed.folder,
            parse_supported=parsed.parse_supported,
            dry_run=False,
            force_reprocess=True,
            password_map=password_map,
            max_files=None,
        )

        report = await build_tax_compliance_report(
            db=db,
            user_id=user_id,
            period_start=date(2024, 4, 1),
            period_end=date(2025, 3, 31),
        )
        artifact_total = (
            await db.execute(
                select(func.count(DocumentArtifact.id)).where(DocumentArtifact.user_id == user_id)
            )
        ).scalar() or 0
        statement_total = (
            await db.execute(select(func.count(Statement.id)).where(Statement.user_id == user_id))
        ).scalar() or 0
        txn_total = (
            await db.execute(
                select(func.count(CanonicalTransaction.id)).where(
                    CanonicalTransaction.user_id == user_id
                )
            )
        ).scalar() or 0

        await db.commit()

    output = {
        "user_id": str(user_id),
        "folder": parsed.folder,
        "import_summary": {
            "discovered": result.discovered,
            "ingested": result.ingested,
            "parsed": result.parsed,
            "skipped": result.skipped,
            "failed": result.failed,
            "by_doc_type": result.by_doc_type,
        },
        "data_counts": {
            "artifacts": int(artifact_total),
            "statements": int(statement_total),
            "canonical_transactions": int(txn_total),
        },
        "tax_totals": {
            "total_income": report["totals"]["total_income"],
            "total_expense": report["totals"]["total_expense"],
            "tax_payments": report["totals"]["tax_payments"],
            "documented_interest_income": report["totals"]["documented_interest_income"],
            "documented_tax_payments": report["totals"]["documented_tax_payments"],
            "savings_account_count": report["totals"]["savings_account_count"],
        },
    }
    print(json.dumps(output, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(_run(_args()))
