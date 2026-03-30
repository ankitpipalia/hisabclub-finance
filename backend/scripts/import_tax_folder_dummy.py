from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date, datetime

from passlib.hash import argon2
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_factory
from app.engines.insights.tax_compliance import build_tax_compliance_report
from app.engines.intake.folder_importer import import_folder
from app.models.canonical_transaction import CanonicalTransaction
from app.models.document_artifact import DocumentArtifact
from app.models.statement import Statement
from app.models.user import User
from app.security.tenant_context import (
    apply_rls_db_role,
    set_request_user_context,
    set_worker_context,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a local tax folder for a dummy user.")
    parser.add_argument("--folder", required=True, help="Absolute folder path to ingest.")
    parser.add_argument(
        "--password-map-json",
        default="",
        help="Optional JSON object for path->PDF password.",
    )
    parser.add_argument(
        "--parse-supported",
        action="store_true",
        help="Parse bank/card statements while importing (slower).",
    )
    return parser.parse_args()


async def _run(folder: str, password_map_json: str, parse_supported: bool) -> None:
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)

    password_map: dict[str, str] | None = None
    if password_map_json.strip():
        loaded = json.loads(password_map_json)
        if isinstance(loaded, dict):
            password_map = {str(k): str(v) for k, v in loaded.items() if str(v).strip()}

    email = f"dummy.taxscan.{datetime.utcnow().strftime('%Y%m%d%H%M%S')}@local.test"
    async with async_session_factory() as db:
        if settings.db_set_role_on_connect:
            await apply_rls_db_role(db, role_name=settings.db_rls_role)

        await set_worker_context(db)
        user = User(
            email=email,
            display_name="Dummy Tax Scan User",
            password_hash=argon2.hash("Dummy@12345"),
            first_name="ANKIT",
            date_of_birth="17022002",
        )
        db.add(user)
        await db.flush()

        await set_request_user_context(db, user_id=user.id)
        result = await import_folder(
            db=db,
            user_id=user.id,
            folder_path=folder,
            parse_supported=parse_supported,
            dry_run=False,
            force_reprocess=True,
            password_map=password_map,
            max_files=None,
        )

        report = await build_tax_compliance_report(
            db=db,
            user_id=user.id,
            period_start=date(2024, 4, 1),
            period_end=date(2025, 3, 31),
        )
        artifact_total = (
            await db.execute(
                select(func.count(DocumentArtifact.id)).where(DocumentArtifact.user_id == user.id)
            )
        ).scalar() or 0
        statement_total = (
            await db.execute(select(func.count(Statement.id)).where(Statement.user_id == user.id))
        ).scalar() or 0
        txn_total = (
            await db.execute(
                select(func.count(CanonicalTransaction.id)).where(
                    CanonicalTransaction.user_id == user.id
                )
            )
        ).scalar() or 0

        await db.commit()

    output = {
        "dummy_user_email": email,
        "dummy_user_id": str(user.id),
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
            "tax_financial_year": report["tax_financial_year"],
            "total_income": report["totals"]["total_income"],
            "total_expense": report["totals"]["total_expense"],
            "tax_payments": report["totals"]["tax_payments"],
            "documented_interest_income": report["totals"]["documented_interest_income"],
            "documented_tax_payments": report["totals"]["documented_tax_payments"],
            "documented_fd_principal": report["totals"]["documented_fd_principal"],
            "documented_ppf_contribution": report["totals"]["documented_ppf_contribution"],
            "savings_account_count": report["totals"]["savings_account_count"],
        },
        "linkage_checks": report["linkage_checks"],
    }
    print(json.dumps(output, ensure_ascii=True))


if __name__ == "__main__":
    parsed = _args()
    asyncio.run(_run(parsed.folder, parsed.password_map_json, parsed.parse_supported))
