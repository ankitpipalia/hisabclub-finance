import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, desc, select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.intake.doc_classifier import (
    classify_document,
    classify_uploaded_pdf,
    normalize_doc_type_hint,
)
from app.engines.intake.tax_document_parser import extract_tax_document_metadata
from app.engines.jobs.service import enqueue_parse_job, list_dlq_jobs, requeue_dlq_job
from app.engines.llm.knowledge import ingest_pdf_knowledge
from app.engines.parser.base import StatementDuplicateError
from app.engines.parser.hints import normalize_parser_hints
from app.engines.parser.password_patterns import resolve_pdf_password
from app.engines.parser.pdf_utils import decrypt_pdf
from app.engines.parser.pdf_utils import extract_text as extract_pdf_text
from app.models.document_artifact import DocumentArtifact
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.extraction_job import ExtractionJob
from app.models.institution_parser_support import InstitutionParserSupport
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.schemas.upload import (
    BulkUploadResponse,
    BulkUploadResultItem,
    ExtractionJobResponse,
    ParserHealthItemResponse,
    UploadResponse,
    UploadReviewItemResponse,
    UploadStatusResponse,
)
from app.security.crypto import encrypt_text

router = APIRouter()

_STATEMENT_DOC_TYPES = {"bank_statement", "credit_card_statement"}
_SUPPORTED_NON_PDF_UPLOAD_EXTS = {".xlsx", ".xls", ".csv"}
_SUPPORTED_UPLOAD_EXTS = {".pdf", *_SUPPORTED_NON_PDF_UPLOAD_EXTS}


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


async def _register_non_statement_pdf(
    *,
    db: DbSession,
    user_id: uuid.UUID,
    content: bytes,
    file_name: str,
    file_size: int,
    file_hash: str,
    encrypted: bool,
    password: str | None,
    bank_hint: str | None,
    account_type_hint: str | None,
    doc_type: str,
    force_reprocess: bool,
    extracted_text: str | None,
) -> UploadResponse:
    existing = (
        await db.execute(
            select(DocumentArtifact)
            .where(
                DocumentArtifact.user_id == user_id,
                DocumentArtifact.file_hash_sha256 == file_hash,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None and not force_reprocess:
        existing_name = (existing.file_name or "").strip()
        duplicate_ref = f" ({existing_name})" if existing_name else ""
        return UploadResponse(
            pdf_id=str(existing.id),
            document_id=str(existing.id),
            status="duplicate",
            message=(
                f"This document matches a previously uploaded file{duplicate_ref}. "
                "Enable reprocess to register it again."
            ),
            bank_name=bank_hint,
            account_type=doc_type,
        )

    storage_dir = os.path.join(settings.upload_dir, str(user_id), "artifacts")
    os.makedirs(storage_dir, exist_ok=True)
    artifact_id = existing.id if existing is not None else uuid.uuid4()
    storage_path = os.path.join(storage_dir, f"{artifact_id}.pdf")
    with open(storage_path, "wb") as out:
        out.write(content)

    metadata = extract_tax_document_metadata(
        doc_type=doc_type,
        text=extracted_text or "",
        source_filename=file_name,
    )
    if bank_hint:
        metadata["bank_hint"] = bank_hint
    if account_type_hint:
        metadata["account_type_hint"] = account_type_hint

    if existing is None:
        artifact = DocumentArtifact(
            id=artifact_id,
            user_id=user_id,
            file_path=storage_path,
            file_name=file_name,
            file_ext="pdf",
            file_hash_sha256=file_hash,
            file_size_bytes=file_size,
            doc_type=doc_type,
            bank_hint=bank_hint,
            status="parsed",
            parse_message=f"Registered {doc_type} document for tax assessment.",
            metadata_json=metadata,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(artifact)
    else:
        artifact = existing
        artifact.file_path = storage_path
        artifact.file_name = file_name
        artifact.file_ext = "pdf"
        artifact.file_size_bytes = file_size
        artifact.doc_type = doc_type
        artifact.bank_hint = bank_hint
        artifact.status = "parsed"
        artifact.parse_message = f"Registered {doc_type} document for tax assessment."
        artifact.metadata_json = metadata
        artifact.processed_at = datetime.now(timezone.utc)
    await db.flush()

    try:
        await ingest_pdf_knowledge(
            db=db,
            user_id=user_id,
            pdf_content=content,
            password=password,
            source_filename=file_name,
            source_kind="artifact",
            artifact_id=artifact.id,
            bank_hint=bank_hint,
            account_type_hint=account_type_hint,
            doc_type=doc_type,
        )
    except Exception:
        pass

    return UploadResponse(
        pdf_id=str(artifact.id),
        document_id=str(artifact.id),
        status="success",
        message=(
            "Document registered for tax assessment. "
            "It will be linked in your new-regime tax view."
        ),
        bank_name=bank_hint,
        account_type=doc_type,
    )


async def _register_non_pdf_artifact(
    *,
    db: DbSession,
    user_id: uuid.UUID,
    content: bytes,
    file_name: str,
    file_ext: str,
    file_size: int,
    file_hash: str,
    bank_hint: str | None,
    account_type_hint: str | None,
    doc_type: str,
    force_reprocess: bool,
) -> UploadResponse:
    existing = (
        await db.execute(
            select(DocumentArtifact)
            .where(
                DocumentArtifact.user_id == user_id,
                DocumentArtifact.file_hash_sha256 == file_hash,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None and not force_reprocess:
        existing_name = (existing.file_name or "").strip()
        duplicate_ref = f" ({existing_name})" if existing_name else ""
        return UploadResponse(
            pdf_id=str(existing.id),
            document_id=str(existing.id),
            status="duplicate",
            message=(
                f"This document matches a previously uploaded file{duplicate_ref}. "
                "Enable reprocess to register it again."
            ),
            bank_name=bank_hint,
            account_type=doc_type,
        )

    storage_dir = os.path.join(settings.upload_dir, str(user_id), "artifacts")
    os.makedirs(storage_dir, exist_ok=True)
    artifact_id = existing.id if existing is not None else uuid.uuid4()
    ext = (file_ext or "").lower().lstrip(".") or "bin"
    storage_path = os.path.join(storage_dir, f"{artifact_id}.{ext}")
    with open(storage_path, "wb") as out:
        out.write(content)

    extracted_text = ""
    if ext == "csv":
        extracted_text = content.decode("utf-8", errors="ignore")[:30000]

    metadata = extract_tax_document_metadata(
        doc_type=doc_type,
        text=extracted_text,
        source_filename=file_name,
    )
    if bank_hint:
        metadata["bank_hint"] = bank_hint
    if account_type_hint:
        metadata["account_type_hint"] = account_type_hint

    if existing is None:
        artifact = DocumentArtifact(
            id=artifact_id,
            user_id=user_id,
            file_path=storage_path,
            file_name=file_name,
            file_ext=ext,
            file_hash_sha256=file_hash,
            file_size_bytes=file_size,
            doc_type=doc_type,
            bank_hint=bank_hint,
            status="parsed",
            parse_message=f"Registered {doc_type} document for tax assessment.",
            metadata_json=metadata,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(artifact)
    else:
        artifact = existing
        artifact.file_path = storage_path
        artifact.file_name = file_name
        artifact.file_ext = ext
        artifact.file_size_bytes = file_size
        artifact.doc_type = doc_type
        artifact.bank_hint = bank_hint
        artifact.status = "parsed"
        artifact.parse_message = f"Registered {doc_type} document for tax assessment."
        artifact.metadata_json = metadata
        artifact.processed_at = datetime.now(timezone.utc)
    await db.flush()

    return UploadResponse(
        pdf_id=str(artifact.id),
        document_id=str(artifact.id),
        status="success",
        message=(
            "Document registered for tax assessment. "
            "It will be linked in your new-regime tax view."
        ),
        bank_name=bank_hint,
        account_type=doc_type,
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

    artifacts = (
        await db.execute(
            select(DocumentArtifact)
            .where(DocumentArtifact.user_id == user.id)
            .where(DocumentArtifact.doc_type.notin_(_STATEMENT_DOC_TYPES))
            .order_by(desc(DocumentArtifact.discovered_at))
            .limit(safe_limit)
        )
    ).scalars().all()
    for artifact in artifacts:
        normalized_status = (artifact.status or "").lower()
        if normalized_status == "parsed":
            status_value = "success"
        elif normalized_status in {"failed"}:
            status_value = "failed"
        elif normalized_status in {"discovered"}:
            status_value = "reviewing"
        else:
            status_value = "error"
        items.append(
            UploadReviewItemResponse(
                pdf_id=str(artifact.id),
                document_id=str(artifact.id),
                file_name=artifact.file_name,
                status=status_value,
                message=artifact.parse_message or "Document registered for tax assessment.",
                bank_name=artifact.bank_hint,
                account_type=artifact.doc_type,
                created_at=(
                    artifact.processed_at.isoformat()
                    if artifact.processed_at
                    else artifact.discovered_at.isoformat()
                ),
            )
        )

    items.sort(key=lambda item: item.created_at or "", reverse=True)
    if len(items) > safe_limit:
        return items[:safe_limit]
    return items


@router.post("/pdf", response_model=UploadResponse)
async def upload_pdf(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    bank_hint: str | None = Form(None),
    account_type_hint: str | None = Form(None),
    document_type_hint: str | None = Form(None),
    force_reprocess: bool = Form(False),
):
    """Upload a supported document (PDF/XLSX/XLS/CSV)."""
    if not isinstance(password, str):
        password = None
    if not isinstance(bank_hint, str):
        bank_hint = None
    if not isinstance(account_type_hint, str):
        account_type_hint = None
    if not isinstance(document_type_hint, str):
        document_type_hint = None
    if not isinstance(force_reprocess, bool):
        force_reprocess = False

    file_name = (file.filename or "").strip()
    file_ext = os.path.splitext(file_name)[1].lower()
    if not file_name or file_ext not in _SUPPORTED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: .pdf, .xlsx, .xls, .csv",
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
    normalized_doc_type_hint = normalize_doc_type_hint(document_type_hint)
    auto_mode = normalized_doc_type_hint in {None, "auto"}

    if file_ext in _SUPPORTED_NON_PDF_UPLOAD_EXTS:
        resolved_bank_hint = hints.bank_hint
        resolved_account_type_hint = hints.account_type_hint
        if auto_mode:
            classified = classify_document(file_name)
            doc_type = classified.doc_type
            resolved_bank_hint = resolved_bank_hint or classified.bank_hint
            resolved_account_type_hint = (
                resolved_account_type_hint or classified.account_type_hint
            )
        else:
            doc_type = normalized_doc_type_hint or "unknown_pdf"

        if doc_type in {"spreadsheet", "unknown_pdf", "unsupported"}:
            return UploadResponse(
                pdf_id=str(uuid.uuid4()),
                document_id=None,
                status="review_required",
                message=(
                    "Auto-detect is uncertain for this spreadsheet. "
                    "Please choose the document type manually and re-upload."
                ),
                bank_name=resolved_bank_hint,
                account_type=resolved_account_type_hint,
            )

        if doc_type in _STATEMENT_DOC_TYPES:
            return UploadResponse(
                pdf_id=str(uuid.uuid4()),
                document_id=None,
                status="review_required",
                message=(
                    "Spreadsheet bank/card statement parsing is not supported yet. "
                    "Upload statement PDFs or choose the correct non-statement type."
                ),
                bank_name=resolved_bank_hint,
                account_type=resolved_account_type_hint,
            )

        file_hash = hashlib.sha256(content).hexdigest()
        return await _register_non_pdf_artifact(
            db=db,
            user_id=user.id,
            content=content,
            file_name=file_name,
            file_ext=file_ext,
            file_size=file_size,
            file_hash=file_hash,
            bank_hint=resolved_bank_hint,
            account_type_hint=resolved_account_type_hint,
            doc_type=doc_type,
            force_reprocess=force_reprocess,
        )

    try:
        password_resolution = await resolve_pdf_password(
            db=db,
            user_id=user.id,
            pdf_content=content,
            bank_hint=hints.bank_hint,
            account_type_hint=hints.account_type_hint,
            source_filename=file_name,
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

    extracted_text = ""
    try:
        classification_bytes = decrypt_pdf(content, resolved_password)
        classification_pages = extract_pdf_text(classification_bytes)
        extracted_text = "\n".join(classification_pages)
    except Exception:
        extracted_text = ""

    legacy_statement_mode = document_type_hint is None
    resolved_bank_hint = hints.bank_hint
    resolved_account_type_hint = hints.account_type_hint
    if legacy_statement_mode:
        doc_type = (
            "credit_card_statement"
            if hints.account_type_hint == "credit_card"
            else "bank_statement"
        )
    else:
        auto_mode = (document_type_hint or "").strip().lower() in {"", "auto"}
        classified = classify_uploaded_pdf(
            filename=file_name,
            extracted_text=extracted_text,
            bank_hint=hints.bank_hint,
            account_type_hint=hints.account_type_hint,
            document_type_hint=document_type_hint,
        )
        doc_type = classified.doc_type
        resolved_bank_hint = resolved_bank_hint or classified.bank_hint
        resolved_account_type_hint = (
            resolved_account_type_hint or classified.account_type_hint
        )
        if settings.llm_enabled and auto_mode and (
            doc_type == "unknown_pdf" or classified.confidence < 0.72
        ):
            try:
                from app.engines.llm.client import LLMClient
                from app.engines.llm.document_classifier import (
                    llm_classify_uploaded_document,
                )
                from app.engines.llm.router import route_model_for_task

                llm_client = LLMClient(
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                )
                llm_model = route_model_for_task(task="document_classification")
                llm_classified = await llm_classify_uploaded_document(
                    llm_client,
                    filename=file_name,
                    extracted_text=extracted_text,
                    deterministic=classified,
                    model=llm_model,
                )
                if (
                    llm_classified is not None
                    and llm_classified.confidence >= 0.62
                    and llm_classified.doc_type != "unknown_pdf"
                ):
                    doc_type = llm_classified.doc_type
                    resolved_bank_hint = llm_classified.bank_hint or resolved_bank_hint
                    resolved_account_type_hint = (
                        llm_classified.account_type_hint or resolved_account_type_hint
                    )
            except Exception:
                pass

        if auto_mode and doc_type == "unknown_pdf":
            return UploadResponse(
                pdf_id=str(uuid.uuid4()),
                document_id=None,
                status="review_required",
                message=(
                    "Auto-detect is uncertain for this PDF. "
                    "Please choose the document type manually and re-upload."
                ),
                bank_name=resolved_bank_hint,
                account_type=resolved_account_type_hint,
            )

        if resolved_account_type_hint is None and doc_type == "credit_card_statement":
            resolved_account_type_hint = "credit_card"
        elif resolved_account_type_hint is None and doc_type == "bank_statement":
            resolved_account_type_hint = "bank_account"

    # Hash for dedup
    file_hash = hashlib.sha256(content).hexdigest()

    if doc_type not in _STATEMENT_DOC_TYPES:
        return await _register_non_statement_pdf(
            db=db,
            user_id=user.id,
            content=content,
            file_name=file_name,
            file_size=file_size,
            file_hash=file_hash,
            encrypted=password_resolution.encrypted,
            password=resolved_password,
            bank_hint=resolved_bank_hint,
            account_type_hint=resolved_account_type_hint,
            doc_type=doc_type,
            force_reprocess=force_reprocess,
            extracted_text=extracted_text,
        )

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
        existing_pdf_name = (
            (
                await db.execute(
                    select(RawPdf.original_filename)
                    .where(RawPdf.user_id == user.id, RawPdf.id == existing_pdf_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            or ""
        )
        duplicate_ref = f" ({existing_pdf_name})" if existing_pdf_name else ""
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This PDF matches a previously uploaded statement"
                f"{duplicate_ref}. Enable reprocess to parse it again."
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
        original_filename=file_name,
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
            source_filename=file_name,
            source_kind="raw_pdf",
            raw_pdf_id=pdf_id,
            bank_hint=resolved_bank_hint,
            account_type_hint=resolved_account_type_hint,
            doc_type=doc_type,
        )
    except Exception:
        pass  # Knowledge ingest is best-effort; parsing should still continue.

    try:
        payload: dict[str, str | bool] = {
            "bank_hint": resolved_bank_hint or "",
            "account_type_hint": resolved_account_type_hint or "",
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
            bank_name=resolved_bank_hint,
            account_type=resolved_account_type_hint,
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
            bank_name=resolved_bank_hint,
            account_type=resolved_account_type_hint,
        )
    except Exception as e:
        return UploadResponse(
            pdf_id=str(pdf_id),
            document_id=str(pdf_id),
            status="failed",
            message=str(e),
            bank_name=resolved_bank_hint,
            account_type=resolved_account_type_hint,
        )


@router.post("/pdfs", response_model=BulkUploadResponse)
async def upload_pdfs(
    user: CurrentUser,
    db: DbSession,
    files: list[UploadFile] = File(...),
    items_json: str | None = Form(None),
    password: str | None = Form(None),
    bank_hint: str | None = Form(None),
    account_type_hint: str | None = Form(None),
    document_type_hint: str | None = Form(None),
    force_reprocess: bool = Form(False),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required.",
        )

    per_file_items: list[dict] = []
    if items_json:
        try:
            parsed = json.loads(items_json)
            if isinstance(parsed, list):
                per_file_items = [item for item in parsed if isinstance(item, dict)]
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="items_json must be a valid JSON array.",
            ) from exc

    results: list[BulkUploadResultItem] = []
    success_count = 0
    reviewing_count = 0
    failed_count = 0
    duplicate_count = 0

    def _optional_str(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    for idx, uploaded_file in enumerate(files):
        item = per_file_items[idx] if idx < len(per_file_items) else {}
        file_name = uploaded_file.filename or f"file-{idx + 1}"
        try:
            response = await upload_pdf(
                user=user,
                db=db,
                file=uploaded_file,
                password=_optional_str(item.get("password")) or password,
                bank_hint=_optional_str(item.get("bank_hint")) or bank_hint,
                account_type_hint=(
                    _optional_str(item.get("account_type_hint")) or account_type_hint
                ),
                document_type_hint=(
                    _optional_str(item.get("document_type_hint")) or document_type_hint
                ),
                force_reprocess=bool(item.get("force_reprocess", force_reprocess)),
            )
        except HTTPException as exc:
            detail = str(exc.detail or "Upload failed.")
            status_value = "duplicate" if exc.status_code == status.HTTP_409_CONFLICT else "failed"
            response = UploadResponse(
                pdf_id=str(uuid.uuid4()),
                document_id=None,
                status=status_value,
                message=detail,
            )

        if response.status in {"success", "parsed"}:
            success_count += 1
        elif response.status in {
            "reviewing",
            "uploaded",
            "queued",
            "classifying",
            "extracting",
            "validating",
        }:
            reviewing_count += 1
        elif response.status == "duplicate":
            duplicate_count += 1
        else:
            failed_count += 1

        results.append(
            BulkUploadResultItem(
                file_name=file_name,
                pdf_id=response.pdf_id,
                document_id=response.document_id,
                status=response.status,
                message=response.message,
                bank_name=response.bank_name,
                account_type=response.account_type,
            )
        )

    return BulkUploadResponse(
        total=len(results),
        success_count=success_count,
        reviewing_count=reviewing_count,
        duplicate_count=duplicate_count,
        failed_count=failed_count,
        items=results,
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
