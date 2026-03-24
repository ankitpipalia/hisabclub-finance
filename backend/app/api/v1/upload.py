import hashlib
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.transfer_reclassifier import reclassify_transfer_payments_for_user
from app.engines.parser.base import parse_statement
from app.engines.parser.pdf_utils import decrypt_pdf
from app.engines.parser.pdf_utils import extract_text as extract_pdf_text
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.schemas.upload import UploadResponse, UploadStatusResponse

router = APIRouter()


@router.post("/pdf", response_model=UploadResponse)
async def upload_pdf(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    bank_hint: str | None = Form(None),
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
        is_password_protected=password is not None,
    )
    db.add(raw_pdf)
    await db.flush()

    # Save decrypted text for debugging
    try:
        debug_bytes = decrypt_pdf(content, password)
        debug_pages = extract_pdf_text(debug_bytes)
        debug_text = "\n---PAGE BREAK---\n".join(debug_pages)
        debug_path = os.path.join(storage_dir, f"{pdf_id}_text.txt")
        with open(debug_path, "w") as df:
            df.write(debug_text)
    except Exception:
        pass  # Debug text extraction is best-effort

    # Parse synchronously for MVP
    try:
        statement = await parse_statement(
            db=db,
            user_id=user.id,
            pdf_id=pdf_id,
            pdf_content=content,
            password=password,
            bank_hint=bank_hint,
        )
        parsed_count = statement.transaction_count or 0
        parsed_message = (
            f"Reprocessed {parsed_count} transactions from {statement.bank_name}"
            if is_reprocess
            else f"Parsed {parsed_count} transactions from {statement.bank_name}"
        )
        if parsed_count > 0:
            # Re-run transfer/card-payment intelligence so new statements are
            # integrated with existing account legs immediately.
            await reclassify_transfer_payments_for_user(
                db=db,
                user_id=user.id,
                days=3650,
                limit=10000,
                max_gap_days=7,
                use_llm=True,
            )
        return UploadResponse(
            pdf_id=str(pdf_id),
            status="success",
            message=parsed_message,
        )
    except Exception as e:
        return UploadResponse(
            pdf_id=str(pdf_id),
            status="failed",
            message=str(e),
        )


@router.get("/{pdf_id}/status", response_model=UploadStatusResponse)
async def get_upload_status(pdf_id: str, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(Statement).where(
            Statement.user_id == user.id, Statement.pdf_id == pdf_id
        )
    )
    statement = result.scalar_one_or_none()

    if not statement:
        # Check if PDF exists at all
        pdf_result = await db.execute(
            select(RawPdf).where(RawPdf.id == pdf_id, RawPdf.user_id == user.id)
        )
        if not pdf_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return UploadStatusResponse(pdf_id=pdf_id, status="pending")

    return UploadStatusResponse(
        pdf_id=pdf_id,
        status=statement.parse_status,
        statement_id=str(statement.id),
        transaction_count=statement.transaction_count,
        error=str(statement.parse_errors) if statement.parse_errors else None,
        bank_name=statement.bank_name,
    )
