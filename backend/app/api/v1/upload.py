import hashlib
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, desc, select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.jobs.service import enqueue_parse_job, list_dlq_jobs, requeue_dlq_job
from app.engines.llm.knowledge import ingest_pdf_knowledge
from app.engines.parser.base import StatementDuplicateError
from app.engines.parser.hints import normalize_parser_hints
from app.engines.parser.password_patterns import resolve_pdf_password
from app.engines.parser.pdf_utils import decrypt_pdf
from app.engines.parser.pdf_utils import extract_text as extract_pdf_text
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.extraction_job import ExtractionJob
from app.models.institution_parser_support import InstitutionParserSupport
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.schemas.upload import (
    ExtractionJobResponse,
    ParserHealthItemResponse,
    UploadResponse,
    UploadReviewItemResponse,
    UploadStatusResponse,
)
from app.security.crypto import encrypt_text

router = APIRouter()


def _map_statement_parse_status_to_review_status(parse_status: str | None) -> str:
    normalized = (parse_status or "").strip().lower()
    if normalized in {"uploaded", "classifying", "extracting", "validating"}:
        return "reviewing"
    if normalized == "parsed":
        return "success"
    if normalized == "review_required":
        return "review_required"
    if normalized == "partial":
        return "error"
    if normalized == "failed":
        return "failed"
    return "reviewing"


def _job_review_state(job: ExtractionJob) -> tuple[str, str]:
    if job.status in {"queued", "running"}:
        stage = (job.current_stage or "queued").replace("_", " ")
        return (
            "reviewing",
            f"Document is under review by the local LLM. Stage: {stage}.",
        )
    if job.status == "completed":
        result = job.result_json or {}
        result_status = str(result.get("status", "")).strip().lower()
        if result_status == "duplicate":
            return "duplicate", str(result.get("message") or "Duplicate statement")
        if result_status in {"parsed", "success"}:
            tx_count = int(result.get("transaction_count") or 0)
            return "success", f"Parsed {tx_count} transactions."
        if result_status in {"partial", "review_required"}:
            if result_status == "review_required":
                return (
                    "review_required",
                    "Review required. Some low-confidence transactions were quarantined.",
                )
            return (
                "error",
                "Review required. Some transactions could not be validated automatically.",
            )
        return "reviewing", "Document processing completed. Waiting for statement materialization."
    if job.status == "dlq":
        return "failed", str(job.error_message or "Parsing failed and moved to retry queue.")
    if job.status == "failed":
        return "failed", str(job.error_message or "Parsing failed.")
    return "reviewing", "Document is queued for parsing."


def _to_extraction_job_response(job: ExtractionJob) -> ExtractionJobResponse:
    return ExtractionJobResponse(
        id=str(job.id),
        document_id=str(job.raw_pdf_id),
        status=job.status,
        current_stage=job.current_stage,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        dlq_retry_count=job.dlq_retry_count,
        error_code=job.error_code,
        error_message=job.error_message,
        statement_id=str(job.statement_id) if job.statement_id else None,
        created_at=job.created_at,
        next_run_at=job.next_run_at,
        finished_at=job.finished_at,
    )


@router.get("/recent", response_model=list[UploadReviewItemResponse])
async def list_recent_uploads(user: CurrentUser, db: DbSession, limit: int = 20):
    safe_limit = max(1, min(limit, 100))
    pdfs = (
        await db.execute(
            select(RawPdf)
            .where(RawPdf.user_id == user.id)
            .order_by(desc(RawPdf.ingested_at))
            .limit(safe_limit)
        )
    ).scalars().all()
    pdf_ids = [pdf.id for pdf in pdfs]
    statements = (
        await db.execute(
            select(Statement).where(
                Statement.user_id == user.id,
                Statement.pdf_id.in_(pdf_ids),
            )
        )
    ).scalars().all() if pdf_ids else []
    jobs = (
        await db.execute(
            select(ExtractionJob)
            .where(ExtractionJob.user_id == user.id, ExtractionJob.raw_pdf_id.in_(pdf_ids))
            .order_by(desc(ExtractionJob.created_at))
        )
    ).scalars().all() if pdf_ids else []
    statement_by_pdf_id = {
        statement.pdf_id: statement for statement in statements if statement.pdf_id
    }
    latest_job_by_pdf_id: dict[uuid.UUID, ExtractionJob] = {}
    for job in jobs:
        if job.raw_pdf_id not in latest_job_by_pdf_id:
            latest_job_by_pdf_id[job.raw_pdf_id] = job

    items: list[UploadReviewItemResponse] = []
    for pdf in pdfs:
        statement = statement_by_pdf_id.get(pdf.id)
        latest_job = latest_job_by_pdf_id.get(pdf.id)
        if statement:
            item_status = _map_statement_parse_status_to_review_status(statement.parse_status)
            if item_status == "success":
                message = (
                    f"Parsed {statement.transaction_count or 0} transactions "
                    f"from {statement.bank_name}"
                )
            elif item_status == "error":
                message = (
                    f"Review required for {statement.bank_name}. "
                    f"Parser {statement.parser_used} extracted "
                    f"{statement.transaction_count or 0} transactions."
                )
            elif item_status == "review_required":
                message = (
                    f"Review required for {statement.bank_name}. "
                    f"{statement.quarantined_row_count or 0} transaction(s) are in quarantine."
                )
            elif item_status == "failed":
                message = str(statement.parse_errors or "Statement review failed")
            else:
                message = (
                    "Document is under review by the local LLM. "
                    "Please wait. We will notify you once it completes."
                )
            items.append(
                UploadReviewItemResponse(
                    pdf_id=str(pdf.id),
                    document_id=str(pdf.id),
                    file_name=pdf.original_filename,
                    status=item_status,
                    message=message,
                    bank_name=statement.bank_name,
                    account_type=statement.account_type,
                    parser_used=statement.parser_used,
                    transaction_count=statement.transaction_count,
                    created_at=(
                        statement.parsed_at.isoformat()
                        if statement.parsed_at
                        else pdf.ingested_at.isoformat()
                    ),
                )
            )
            continue

        if latest_job is not None:
            job_status, job_message = _job_review_state(latest_job)
            items.append(
                UploadReviewItemResponse(
                    pdf_id=str(pdf.id),
                    document_id=str(pdf.id),
                    file_name=pdf.original_filename,
                    status=job_status,
                    message=job_message,
                    created_at=pdf.ingested_at.isoformat(),
                )
            )
            continue

        items.append(
            UploadReviewItemResponse(
                pdf_id=str(pdf.id),
                document_id=str(pdf.id),
                file_name=pdf.original_filename,
                status="reviewing",
                message=(
                    "Document is under review by the local LLM. "
                    "Please wait. We will notify you once it completes."
                ),
                created_at=pdf.ingested_at.isoformat(),
            )
        )
    return items


@router.post("/pdf", response_model=UploadResponse)
async def upload_pdf(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    bank_hint: str | None = Form(None),
    account_type_hint: str | None = Form(None),
    force_reprocess: bool = Form(False),
):
    """Upload a PDF statement for parsing."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    content = await file.read()
    file_size = len(content)
    max_size = settings.max_upload_size_mb * 1024 * 1024

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {settings.max_upload_size_mb}MB",
        )

    hints = normalize_parser_hints(bank_hint=bank_hint, account_type_hint=account_type_hint)
    try:
        password_resolution = await resolve_pdf_password(
            db=db,
            user_id=user.id,
            pdf_content=content,
            bank_hint=hints.bank_hint,
            account_type_hint=hints.account_type_hint,
            source_filename=file.filename,
            manual_password=password,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The uploaded file could not be opened as a valid PDF. "
                "Please verify the file and try again."
            ),
        ) from exc
    resolved_password = password_resolution.password
    if password and password_resolution.manual_password_rejected and resolved_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The provided PDF password is incorrect.",
        )
    if password_resolution.encrypted and resolved_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This PDF is password-protected and no saved password pattern matched. "
                "Provide the password manually or configure a password pattern."
            ),
        )

    # Hash for dedup
    file_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicate. `limit(1)` avoids MultipleResultsFound when reprocess
    # creates more than one row for the same hash.
    result = await db.execute(
        select(RawPdf.id)
        .where(RawPdf.user_id == user.id, RawPdf.file_hash_sha256 == file_hash)
        .limit(1)
    )
    existing_pdf_id = result.scalar_one_or_none()
    is_reprocess = existing_pdf_id is not None and force_reprocess
    if existing_pdf_id is not None and not force_reprocess:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This PDF has already been uploaded. "
                "Enable reprocess to parse it again."
            ),
        )

    # Save file to disk
    pdf_id = uuid.uuid4()
    storage_dir = os.path.join(settings.upload_dir, str(user.id))
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, f"{pdf_id}.pdf")

    with open(storage_path, "wb") as f:
        f.write(content)

    # Create raw PDF record
    raw_pdf = RawPdf(
        id=pdf_id,
        user_id=user.id,
        source_type="manual_reprocess" if is_reprocess else "manual_upload",
        original_filename=file.filename,
        file_hash_sha256=file_hash,
        storage_path=storage_path,
        file_size_bytes=file_size,
        is_password_protected=password_resolution.encrypted,
    )
    db.add(raw_pdf)
    await db.flush()

    # Save decrypted text for debugging
    try:
        debug_bytes = decrypt_pdf(content, resolved_password)
        debug_pages = extract_pdf_text(debug_bytes)
        debug_text = "\n---PAGE BREAK---\n".join(debug_pages)
        debug_path = os.path.join(storage_dir, f"{pdf_id}_text.txt")
        with open(debug_path, "w") as df:
            df.write(debug_text)
    except Exception:
        pass  # Debug text extraction is best-effort

    try:
        await ingest_pdf_knowledge(
            db=db,
            user_id=user.id,
            pdf_content=content,
            password=resolved_password,
            source_filename=file.filename,
            source_kind="raw_pdf",
            raw_pdf_id=pdf_id,
            bank_hint=hints.bank_hint,
            account_type_hint=hints.account_type_hint,
            doc_type=(
                "credit_card_statement"
                if hints.account_type_hint == "credit_card"
                else "bank_statement"
            ),
        )
    except Exception:
        pass  # Knowledge ingest is best-effort; parsing should still continue.

    try:
        payload: dict[str, str | bool] = {
            "bank_hint": hints.bank_hint or "",
            "account_type_hint": hints.account_type_hint or "",
            "allow_semantic_duplicate": is_reprocess,
        }
        if resolved_password:
            payload["password_enc"] = encrypt_text(resolved_password)
        await enqueue_parse_job(
            db=db,
            user_id=user.id,
            raw_pdf_id=pdf_id,
            payload=payload,
            priority=120 if is_reprocess else 100,
        )
        return UploadResponse(
            pdf_id=str(pdf_id),
            document_id=str(pdf_id),
            status="reviewing",
            message=(
                "Document is under review by the local LLM. Please wait. "
                "We will notify you once it completes."
            ),
            bank_name=hints.bank_hint,
            account_type=hints.account_type_hint,
        )
    except StatementDuplicateError as e:
        # Cleanup transient duplicate artifact so it does not remain stuck as uploaded.
        await db.execute(
            delete(DocumentKnowledgeChunk).where(
                DocumentKnowledgeChunk.user_id == user.id,
                DocumentKnowledgeChunk.raw_pdf_id == pdf_id,
            )
        )
        await db.execute(
            delete(RawPdf).where(RawPdf.user_id == user.id, RawPdf.id == pdf_id)
        )
        await db.flush()
        debug_path = os.path.join(storage_dir, f"{pdf_id}_text.txt")
        for path in (storage_path, debug_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        return UploadResponse(
            pdf_id=str(pdf_id),
            document_id=str(pdf_id),
            status="duplicate",
            message=str(e),
            bank_name=hints.bank_hint,
            account_type=hints.account_type_hint,
        )
    except Exception as e:
        return UploadResponse(
            pdf_id=str(pdf_id),
            document_id=str(pdf_id),
            status="failed",
            message=str(e),
            bank_name=hints.bank_hint,
            account_type=hints.account_type_hint,
        )


@router.get("/{pdf_id}/status", response_model=UploadStatusResponse)
async def get_upload_status(pdf_id: str, user: CurrentUser, db: DbSession):
    try:
        pdf_uuid = uuid.UUID(pdf_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    result = await db.execute(
        select(Statement).where(
            Statement.user_id == user.id, Statement.pdf_id == pdf_uuid
        )
    )
    statement = result.scalar_one_or_none()

    if statement is not None:
        status_value = _map_statement_parse_status_to_review_status(statement.parse_status)
        if status_value == "reviewing":
            message = "Document is under review by the local LLM. Please wait."
        elif status_value == "success":
            message = f"Parsed {statement.transaction_count or 0} transactions."
        elif status_value == "review_required":
            message = (
                "Document parsed with quarantine. "
                f"{statement.quarantined_row_count or 0} transaction(s) need review."
            )
        elif status_value == "error":
            message = "Review required before promotion to canonical ledger."
        else:
            message = (
                str(statement.parse_errors)
                if statement.parse_errors
                else "Statement parsing failed."
            )
        return UploadStatusResponse(
            pdf_id=pdf_id,
            document_id=pdf_id,
            status=status_value,
            statement_id=str(statement.id),
            transaction_count=statement.transaction_count,
            error=None if status_value in {"reviewing", "success", "review_required"} else message,
            bank_name=statement.bank_name,
            message=message,
        )

    pdf_result = await db.execute(
        select(RawPdf).where(RawPdf.id == pdf_uuid, RawPdf.user_id == user.id)
    )
    raw_pdf = pdf_result.scalar_one_or_none()
    if raw_pdf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    latest_job = (
        await db.execute(
            select(ExtractionJob)
            .where(ExtractionJob.user_id == user.id, ExtractionJob.raw_pdf_id == raw_pdf.id)
            .order_by(desc(ExtractionJob.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_job is not None:
        status_value, message = _job_review_state(latest_job)
        return UploadStatusResponse(
            pdf_id=pdf_id,
            document_id=pdf_id,
            status=status_value,
            statement_id=str(latest_job.statement_id) if latest_job.statement_id else None,
            transaction_count=(latest_job.result_json or {}).get("transaction_count"),
            error=message if status_value in {"error", "failed", "duplicate"} else None,
            message=message,
        )

    return UploadStatusResponse(
        pdf_id=pdf_id,
        document_id=pdf_id,
        status="uploaded",
        message="Document upload accepted and waiting for parser job.",
    )


@router.get("/jobs/dlq", response_model=list[ExtractionJobResponse])
async def list_dead_letter_jobs(user: CurrentUser, db: DbSession, limit: int = 50):
    safe_limit = max(1, min(limit, 200))
    rows = await list_dlq_jobs(db=db, user_id=user.id, limit=safe_limit)
    return [_to_extraction_job_response(job) for job in rows]


@router.post("/jobs/{job_id}/requeue", response_model=ExtractionJobResponse)
async def requeue_dead_letter_job(job_id: str, user: CurrentUser, db: DbSession):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job id",
        ) from exc

    job = (
        await db.execute(
            select(ExtractionJob).where(
                ExtractionJob.id == job_uuid,
                ExtractionJob.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status != "dlq":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DLQ jobs can be requeued.",
        )
    updated = await requeue_dlq_job(db=db, job=job)
    return _to_extraction_job_response(updated)


@router.get("/parser-health", response_model=list[ParserHealthItemResponse])
async def parser_health(user: CurrentUser, db: DbSession):
    rows = (
        await db.execute(
            select(InstitutionParserSupport).order_by(
                InstitutionParserSupport.bank_code.asc(),
                InstitutionParserSupport.account_type.asc(),
            )
        )
    ).scalars().all()
    result: list[ParserHealthItemResponse] = []
    for row in rows:
        success = int(row.observed_success_count or 0)
        failure = int(row.observed_failure_count or 0)
        total = success + failure
        success_rate = float(success / total) if total else 0.0
        expected_rows = int(row.observed_expected_rows or 0)
        extracted_rows = int(row.observed_extracted_rows or 0)
        yield_rate = (float(extracted_rows / expected_rows) if expected_rows > 0 else None)
        result.append(
            ParserHealthItemResponse(
                bank_code=row.bank_code,
                account_type=row.account_type,
                parser_id=row.parser_id,
                observed_success_count=success,
                observed_failure_count=failure,
                observed_expected_rows=expected_rows,
                observed_extracted_rows=extracted_rows,
                success_rate=success_rate,
                yield_rate=yield_rate,
            )
        )
    return result
