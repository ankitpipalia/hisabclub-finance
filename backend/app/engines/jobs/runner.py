from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.engines.insights.statement_integrity import build_credit_card_statement_integrity
from app.engines.jobs.service import (
    claim_next_job,
    complete_job,
    fail_or_retry_job,
    requeue_dlq_job,
)
from app.engines.ledger.transfer_reclassifier import reclassify_transfer_payments_for_user
from app.engines.ledger.upi_reconciliation import reconcile_upi_failures_for_user
from app.engines.parser.base import StatementDuplicateError, parse_statement
from app.engines.parser.hints import normalize_bank_hint
from app.engines.parser.password_patterns import resolve_pdf_password
from app.engines.storage.tiering import move_raw_pdf_to_cold_tier
from app.models.extraction_job import ExtractionJob
from app.models.institution_parser_support import InstitutionParserSupport
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.models.statement_period_coverage import StatementPeriodCoverage
from app.security.crypto import decrypt_text
from app.security.tenant_context import apply_rls_db_role, set_worker_context


async def process_one_pending_job(*, worker_id: str) -> bool:
    async with async_session_factory() as db:
        if settings.db_set_role_on_connect:
            await apply_rls_db_role(db, role_name=settings.db_rls_role)
        await set_worker_context(db)
        job = await claim_next_job(db=db, worker_id=worker_id)
        if job is None:
            await db.commit()
            return False

        try:
            await _process_parse_statement_job(db=db, job=job)
            await db.commit()
            return True
        except Exception as exc:
            await fail_or_retry_job(
                db=db,
                job=job,
                error_code="job_processing_failed",
                error_message=str(exc),
                dlq_reason="unhandled_exception",
            )
            await db.commit()
            return True


async def _process_parse_statement_job(*, db: AsyncSession, job: ExtractionJob) -> None:
    if job.job_type != "parse_statement":
        await complete_job(
            db=db,
            job=job,
            statement_id=None,
            result={"status": "ignored", "reason": f"unsupported_job_type:{job.job_type}"},
        )
        return

    raw_pdf = (
        await db.execute(
            select(RawPdf)
            .where(RawPdf.id == job.raw_pdf_id, RawPdf.user_id == job.user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if raw_pdf is None:
        await fail_or_retry_job(
            db=db,
            job=job,
            error_code="raw_pdf_missing",
            error_message="Raw PDF no longer exists for this job.",
            dlq_reason="missing_input",
        )
        return

    resolved_path = _resolve_storage_path(raw_pdf.storage_path)
    if not resolved_path or not os.path.exists(resolved_path):
        await fail_or_retry_job(
            db=db,
            job=job,
            error_code="pdf_file_missing",
            error_message="Source PDF file missing on disk.",
            dlq_reason="missing_input",
        )
        return

    with open(resolved_path, "rb") as f:
        content = f.read()

    payload = job.payload_json or {}
    password = _decode_password(payload)
    bank_hint = payload.get("bank_hint")
    account_type_hint = payload.get("account_type_hint")
    allow_semantic_duplicate = bool(payload.get("allow_semantic_duplicate", False))
    prefer_llm = bool(payload.get("prefer_llm", False))

    if not password:
        resolution = await resolve_pdf_password(
            db=db,
            user_id=job.user_id,
            pdf_content=content,
            bank_hint=str(bank_hint) if bank_hint else None,
            account_type_hint=str(account_type_hint) if account_type_hint else None,
            source_filename=raw_pdf.original_filename,
        )
        if resolution.password:
            password = resolution.password
        elif resolution.encrypted:
            await fail_or_retry_job(
                db=db,
                job=job,
                error_code="password_required",
                error_message=(
                    "PDF is password-protected and no matching password pattern was found. "
                    "Configure a password pattern and requeue the job."
                ),
                dlq_reason="password_required",
            )
            return

    try:
        statement = await parse_statement(
            db=db,
            user_id=job.user_id,
            pdf_id=raw_pdf.id,
            pdf_content=content,
            password=password,
            bank_hint=bank_hint,
            account_type_hint=account_type_hint,
            allow_semantic_duplicate=allow_semantic_duplicate,
            prefer_llm=prefer_llm,
        )
    except StatementDuplicateError as exc:
        await _record_parser_support_observation(
            db=db,
            bank_code=str(bank_hint) if bank_hint else None,
            account_type=str(account_type_hint) if account_type_hint else None,
            parser_id=None,
            success=False,
        )
        await complete_job(
            db=db,
            job=job,
            statement_id=None,
            result={"status": "duplicate", "message": str(exc)},
        )
        return
    except Exception as exc:
        await _record_parser_support_observation(
            db=db,
            bank_code=str(bank_hint) if bank_hint else None,
            account_type=str(account_type_hint) if account_type_hint else None,
            parser_id=None,
            success=False,
        )
        await fail_or_retry_job(
            db=db,
            job=job,
            error_code="parse_failed",
            error_message=str(exc),
            dlq_reason="parse_failed",
        )
        return

    if (statement.transaction_count or 0) > 0:
        await reclassify_transfer_payments_for_user(
            db=db,
            user_id=job.user_id,
            days=3650,
            limit=10000,
            max_gap_days=7,
            use_llm=True,
        )
        await reconcile_upi_failures_for_user(
            db=db,
            user_id=job.user_id,
            days=3650,
            max_gap_days=3,
            limit=10000,
        )

    await _upsert_statement_period_coverage(
        db=db,
        user_id=job.user_id,
        statement=statement,
    )

    integrity = await _build_integrity_gates(
        db=db,
        user_id=job.user_id,
        statement=statement,
    )
    promotion_gates = _apply_post_parse_gates(statement=statement, integrity=integrity)
    await _record_parser_support_observation(
        db=db,
        bank_code=statement.bank_name,
        account_type=statement.account_type,
        parser_id=statement.parser_used,
        success=statement.parse_status in {"parsed", "review_required"},
        expected_rows=statement.expected_row_count,
        extracted_rows=statement.extracted_row_count,
    )
    moved_to_cold = move_raw_pdf_to_cold_tier(raw_pdf)
    await complete_job(
        db=db,
        job=job,
        statement_id=statement.id,
        result={
            "status": statement.parse_status,
            "transaction_count": statement.transaction_count or 0,
            "integrity_gates": integrity,
            "promotion_gates": promotion_gates,
            "storage_tier": "cold" if moved_to_cold else (raw_pdf.storage_tier or "hot"),
        },
    )


async def auto_retry_one_dlq_job(*, worker_id: str) -> bool:
    async with async_session_factory() as db:
        if settings.db_set_role_on_connect:
            await apply_rls_db_role(db, role_name=settings.db_rls_role)
        await set_worker_context(db)
        job = (
            await db.execute(
                select(ExtractionJob)
                .where(
                    ExtractionJob.status == "dlq",
                    ExtractionJob.job_type == "parse_statement",
                    ExtractionJob.dlq_retry_count < 1,
                )
                .order_by(ExtractionJob.finished_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if job is None:
            await db.commit()
            return False

        payload = dict(job.payload_json or {})
        payload["allow_semantic_duplicate"] = True
        payload["prefer_llm"] = True
        job.payload_json = payload
        job.locked_by = worker_id
        await requeue_dlq_job(db=db, job=job)
        await db.commit()
        return True


def _decode_password(payload: dict) -> str | None:
    encrypted = payload.get("password_enc")
    if not encrypted:
        return None
    try:
        return decrypt_text(str(encrypted))
    except Exception:
        return None


def _resolve_storage_path(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    if os.path.exists(storage_path):
        return storage_path
    if storage_path.startswith("/app/uploads/"):
        local = storage_path.removeprefix("/app/uploads/").lstrip("/")
        candidate = os.path.join("./uploads", local)
        if os.path.exists(candidate):
            return candidate
    return storage_path


async def _upsert_statement_period_coverage(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    statement: Statement,
) -> None:
    if not statement.statement_period_start or not statement.statement_period_end:
        return
    row = (
        await db.execute(
            select(StatementPeriodCoverage)
            .where(
                StatementPeriodCoverage.user_id == user_id,
                StatementPeriodCoverage.bank_name == statement.bank_name,
                StatementPeriodCoverage.account_type == statement.account_type,
                StatementPeriodCoverage.account_number_masked == statement.account_number_masked,
                StatementPeriodCoverage.period_start == statement.statement_period_start,
                StatementPeriodCoverage.period_end == statement.statement_period_end,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(
            StatementPeriodCoverage(
                user_id=user_id,
                statement_id=statement.id,
                bank_name=statement.bank_name,
                account_type=statement.account_type,
                account_number_masked=statement.account_number_masked,
                period_start=statement.statement_period_start,
                period_end=statement.statement_period_end,
                is_complete=statement.parse_status == "parsed",
            )
        )
        return
    row.statement_id = statement.id
    row.is_complete = statement.parse_status == "parsed"


async def _build_integrity_gates(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    statement: Statement,
) -> dict | None:
    if statement.account_type != "credit_card":
        return None
    report = await build_credit_card_statement_integrity(
        db=db,
        user_id=user_id,
        statement=statement,
    )
    return {
        "status": report.get("status"),
        "net_activity": report.get("net_activity"),
        "due_gap": report.get("due_gap"),
        "llm_status": report.get("llm_status"),
        "llm_confidence": report.get("llm_confidence"),
    }


async def run_worker_loop(
    *,
    worker_id: str,
    poll_seconds: float,
    enable_dlq_retry: bool = True,
) -> None:
    while True:
        did_work = await process_one_pending_job(worker_id=worker_id)
        if not did_work and enable_dlq_retry:
            await auto_retry_one_dlq_job(worker_id=worker_id)
        if not did_work:
            await asyncio.sleep(poll_seconds)


async def _record_parser_support_observation(
    *,
    db: AsyncSession,
    bank_code: str | None,
    account_type: str | None,
    parser_id: str | None,
    success: bool,
    expected_rows: int | None = None,
    extracted_rows: int | None = None,
) -> None:
    normalized_bank = normalize_bank_hint(bank_code)
    normalized_account = _normalize_account_type_for_support(account_type)
    if not normalized_bank or not normalized_account:
        return
    row = (
        await db.execute(
            select(InstitutionParserSupport)
            .where(
                InstitutionParserSupport.bank_code == normalized_bank,
                InstitutionParserSupport.account_type == normalized_account,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = InstitutionParserSupport(
            bank_code=normalized_bank,
            account_type=normalized_account,
            parser_id=parser_id,
            is_supported=success,
            observed_success_count=1 if success else 0,
            observed_failure_count=0 if success else 1,
            observed_expected_rows=max(0, int(expected_rows or 0)),
            observed_extracted_rows=max(0, int(extracted_rows or 0)),
        )
        db.add(row)
        return
    if parser_id:
        row.parser_id = parser_id
    if success:
        row.observed_success_count = int(row.observed_success_count or 0) + 1
        row.is_supported = True
    else:
        row.observed_failure_count = int(row.observed_failure_count or 0) + 1
    row.observed_expected_rows = int(row.observed_expected_rows or 0) + max(
        0, int(expected_rows or 0)
    )
    row.observed_extracted_rows = int(row.observed_extracted_rows or 0) + max(
        0, int(extracted_rows or 0)
    )


def _normalize_account_type_for_support(account_type: str | None) -> str | None:
    if not account_type:
        return None
    normalized = account_type.strip().lower()
    if normalized in {"bank_account", "savings", "current"}:
        return "bank_account"
    if normalized == "credit_card":
        return "credit_card"
    return None


def _apply_post_parse_gates(
    *,
    statement: Statement,
    integrity: dict | None,
) -> dict:
    quarantine_clear = int(statement.quarantined_row_count or 0) == 0

    expected = int(statement.expected_row_count or 0)
    yield_rate = float(statement.yield_rate) if statement.yield_rate is not None else None
    if expected >= 5:
        yield_rate_ok = (yield_rate or 0.0) >= settings.min_yield_rate_for_auto_promotion
    else:
        yield_rate_ok = True

    integrity_ok = True
    if statement.account_type == "credit_card" and settings.require_cc_integrity_ok_for_auto_promotion:
        integrity_status = (integrity or {}).get("status")
        integrity_ok = integrity_status in {"ok", "pass"}

    validation_payload = dict((statement.parse_errors or {}).get("validation") or {})
    balance_walk = dict(validation_payload.get("balance_walk") or {})
    bank_balance_walk_ok = True
    if statement.account_type in {"savings", "current"} and balance_walk.get("applied"):
        bank_balance_walk_ok = bool(balance_walk.get("ok"))

    all_pass = quarantine_clear and yield_rate_ok and integrity_ok and bank_balance_walk_ok

    if statement.parse_status == "parsed" and not all_pass:
        statement.parse_status = "review_required"

    existing_errors = dict(statement.parse_errors or {})
    existing_errors["promotion_gates"] = {
        "quarantine_clear": quarantine_clear,
        "yield_rate_ok": yield_rate_ok,
        "credit_card_integrity_ok": integrity_ok,
        "bank_balance_walk_ok": bank_balance_walk_ok,
        "all_pass": all_pass,
        "yield_rate": yield_rate,
        "expected_row_count": expected,
    }
    statement.parse_errors = existing_errors
    return existing_errors["promotion_gates"]
