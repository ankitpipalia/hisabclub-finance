from datetime import datetime, timezone
import os

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import literal, func, select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.insights.statement_integrity import build_credit_card_statement_integrity
from app.engines.llm.correction_chat import run_transaction_correction_chat
from app.engines.parser.statement_lifecycle import (
    delete_statement_and_memory,
    rereview_statement_with_llm,
)
from app.models.parsed_transaction import ParsedTransaction
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.models.transaction_annotation import TransactionAnnotation
from app.models.transaction_source import TransactionSource
from app.schemas.auth import MessageResponse
from app.schemas.statement import (
    StatementAnnotationRequest,
    StatementAnnotationResponse,
    StatementIntegrityResponse,
    StatementListResponse,
    StatementReviewResponse,
    StatementReviewTransactionResponse,
    StatementResponse,
)

router = APIRouter()


def _to_statement_response(
    statement: Statement,
    pdf_id: str | None,
    pdf_filename: str | None,
    source_type: str | None,
    reprocess_count: int | None,
) -> StatementResponse:
    safe_reprocess_count = int(reprocess_count or 1)
    is_reprocess = source_type == "manual_reprocess"

    return StatementResponse(
        id=str(statement.id),
        pdf_id=pdf_id,
        pdf_filename=pdf_filename,
        bank_name=statement.bank_name,
        account_type=statement.account_type,
        account_number_masked=statement.account_number_masked,
        statement_period_start=statement.statement_period_start,
        statement_period_end=statement.statement_period_end,
        due_date=statement.due_date,
        min_amount_due=float(statement.min_amount_due) if statement.min_amount_due else None,
        total_amount_due=float(statement.total_amount_due) if statement.total_amount_due else None,
        credit_limit=float(statement.credit_limit) if statement.credit_limit else None,
        opening_balance=float(statement.opening_balance) if statement.opening_balance else None,
        closing_balance=float(statement.closing_balance) if statement.closing_balance else None,
        parser_used=statement.parser_used,
        parse_status=statement.parse_status,
        transaction_count=statement.transaction_count,
        expected_row_count=statement.expected_row_count,
        extracted_row_count=statement.extracted_row_count,
        promoted_row_count=statement.promoted_row_count,
        quarantined_row_count=statement.quarantined_row_count,
        yield_rate=statement.yield_rate,
        source_type=source_type,
        is_reprocess=is_reprocess,
        reprocess_count=safe_reprocess_count,
        created_at=statement.created_at,
    )


def _to_annotation_response(annotation: TransactionAnnotation) -> StatementAnnotationResponse:
    return StatementAnnotationResponse(
        id=str(annotation.id),
        parsed_transaction_id=str(annotation.parsed_transaction_id) if annotation.parsed_transaction_id else None,
        canonical_transaction_id=str(annotation.canonical_transaction_id) if annotation.canonical_transaction_id else None,
        statement_id=str(annotation.statement_id),
        annotation_type=annotation.annotation_type,
        content=annotation.content,
        llm_response=annotation.llm_response,
        status=annotation.status,
        actions_json=annotation.actions_json,
        page_number=annotation.page_number,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


@router.get("", response_model=StatementListResponse)
async def list_statements(
    user: CurrentUser,
    db: DbSession,
    bank: str | None = Query(None),
    account_type: str | None = Query(None),
):
    reprocess_counts = (
        select(
            RawPdf.file_hash_sha256.label("file_hash"),
            func.count(Statement.id).label("reprocess_count"),
        )
        .join(Statement, Statement.pdf_id == RawPdf.id)
        .where(Statement.user_id == user.id)
        .group_by(RawPdf.file_hash_sha256)
        .subquery()
    )

    query = (
        select(
            Statement,
            RawPdf.id.label("pdf_id"),
            RawPdf.original_filename.label("pdf_filename"),
            RawPdf.source_type.label("source_type"),
            func.coalesce(reprocess_counts.c.reprocess_count, 1).label("reprocess_count"),
        )
        .outerjoin(RawPdf, Statement.pdf_id == RawPdf.id)
        .outerjoin(reprocess_counts, reprocess_counts.c.file_hash == RawPdf.file_hash_sha256)
        .where(Statement.user_id == user.id, Statement.is_active == True)  # noqa: E712
    )

    if bank:
        query = query.where(Statement.bank_name == bank.upper())
    if account_type:
        query = query.where(Statement.account_type == account_type)

    query = query.order_by(Statement.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(query)
    rows = result.all()
    items = [
        _to_statement_response(
            statement,
            str(pdf_id) if pdf_id else None,
            pdf_filename,
            source_type,
            reprocess_count,
        )
        for statement, pdf_id, pdf_filename, source_type, reprocess_count in rows
    ]

    return StatementListResponse(
        items=items,
        total=total,
    )


@router.get("/{statement_id}", response_model=StatementResponse)
async def get_statement(statement_id: str, user: CurrentUser, db: DbSession):
    reprocess_counts = (
        select(
            RawPdf.file_hash_sha256.label("file_hash"),
            func.count(Statement.id).label("reprocess_count"),
        )
        .join(Statement, Statement.pdf_id == RawPdf.id)
        .where(Statement.user_id == user.id)
        .group_by(RawPdf.file_hash_sha256)
        .subquery()
    )

    result = await db.execute(
        select(
            Statement,
            RawPdf.id.label("pdf_id"),
            RawPdf.original_filename.label("pdf_filename"),
            RawPdf.source_type.label("source_type"),
            func.coalesce(reprocess_counts.c.reprocess_count, 1).label("reprocess_count"),
        )
        .outerjoin(RawPdf, Statement.pdf_id == RawPdf.id)
        .outerjoin(reprocess_counts, reprocess_counts.c.file_hash == RawPdf.file_hash_sha256)
        .where(Statement.id == statement_id, Statement.user_id == user.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    statement, pdf_id, pdf_filename, source_type, reprocess_count = row

    return _to_statement_response(
        statement,
        str(pdf_id) if pdf_id else None,
        pdf_filename,
        source_type,
        reprocess_count,
    )


@router.get("/{statement_id}/pdf")
async def get_statement_pdf(statement_id: str, user: CurrentUser, db: DbSession):
    row = (
        await db.execute(
            select(RawPdf.storage_path, RawPdf.original_filename)
            .join(Statement, Statement.pdf_id == RawPdf.id)
            .where(Statement.id == statement_id, Statement.user_id == user.id)
            .limit(1)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement PDF not found.",
        )

    storage_path, original_filename = row
    resolved_path = _resolve_storage_path(storage_path)
    if not resolved_path or not os.path.exists(resolved_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF file is missing on disk.",
        )

    download_name = original_filename or f"statement-{statement_id}.pdf"
    return FileResponse(
        path=resolved_path,
        media_type="application/pdf",
        filename=download_name,
        headers={"Content-Disposition": f'inline; filename="{download_name}"'},
    )


@router.get("/{statement_id}/integrity", response_model=StatementIntegrityResponse)
async def get_statement_integrity(statement_id: str, user: CurrentUser, db: DbSession):
    statement = (
        await db.execute(
            select(Statement).where(Statement.id == statement_id, Statement.user_id == user.id)
        )
    ).scalar_one_or_none()
    if statement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if statement.account_type != "credit_card":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integrity check is currently available for credit-card statements only.",
        )

    report = await build_credit_card_statement_integrity(
        db=db,
        user_id=user.id,
        statement=statement,
    )
    return StatementIntegrityResponse(**report)


@router.get("/{statement_id}/review", response_model=StatementReviewResponse)
async def get_statement_review(statement_id: str, user: CurrentUser, db: DbSession):
    row = (
        await db.execute(
            select(
                Statement,
                RawPdf.id.label("pdf_id"),
                RawPdf.original_filename.label("pdf_filename"),
                RawPdf.source_type.label("source_type"),
                literal(1).label("reprocess_count"),
            )
            .outerjoin(RawPdf, Statement.pdf_id == RawPdf.id)
            .where(Statement.id == statement_id, Statement.user_id == user.id)
            .limit(1)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    statement, pdf_id, pdf_filename, source_type, reprocess_count = row

    parsed_transactions = (
        await db.execute(
            select(ParsedTransaction)
            .where(ParsedTransaction.statement_id == statement.id, ParsedTransaction.user_id == user.id)
            .order_by(ParsedTransaction.transaction_date.asc(), ParsedTransaction.created_at.asc())
        )
    ).scalars().all()
    annotations = (
        await db.execute(
            select(TransactionAnnotation)
            .where(TransactionAnnotation.statement_id == statement.id, TransactionAnnotation.user_id == user.id)
            .order_by(TransactionAnnotation.created_at.asc())
        )
    ).scalars().all()
    source_ids = [txn.id for txn in parsed_transactions]
    sources = []
    if source_ids:
        sources = (
            await db.execute(
                select(TransactionSource).where(TransactionSource.parsed_txn_id.in_(source_ids))
            )
        ).scalars().all()
    canonical_by_parsed = {str(source.parsed_txn_id): str(source.canonical_txn_id) for source in sources}
    annotations_by_parsed: dict[str, list[StatementAnnotationResponse]] = {}
    annotation_responses = [_to_annotation_response(annotation) for annotation in annotations]
    for annotation in annotation_responses:
        if annotation.parsed_transaction_id:
            annotations_by_parsed.setdefault(annotation.parsed_transaction_id, []).append(annotation)

    transaction_items = [
        StatementReviewTransactionResponse(
            id=str(txn.id),
            canonical_transaction_id=canonical_by_parsed.get(str(txn.id)),
            transaction_date=txn.transaction_date,
            posting_date=txn.posting_date,
            description_raw=txn.description_raw,
            amount=float(txn.amount),
            direction=txn.direction,
            confidence=float(txn.confidence or 0.0),
            is_quarantined=bool(txn.is_quarantined),
            extraction_method=txn.extraction_method,
            line_number=txn.line_number,
            page_number=None,
            reviewer_user_id=str(txn.reviewer_user_id) if txn.reviewer_user_id else None,
            reviewed_at=txn.reviewed_at,
            annotations=annotations_by_parsed.get(str(txn.id), []),
        )
        for txn in parsed_transactions
    ]

    return StatementReviewResponse(
        statement=_to_statement_response(
            statement,
            str(pdf_id) if pdf_id else None,
            pdf_filename,
            source_type,
            reprocess_count,
        ),
        transactions=transaction_items,
        annotations=annotation_responses,
    )


@router.post(
    "/{statement_id}/transactions/{txn_id}/annotate",
    response_model=StatementAnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def annotate_statement_transaction(
    statement_id: str,
    txn_id: str,
    request: StatementAnnotationRequest,
    user: CurrentUser,
    db: DbSession,
):
    statement = (
        await db.execute(
            select(Statement).where(Statement.id == statement_id, Statement.user_id == user.id)
        )
    ).scalar_one_or_none()
    if statement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    parsed = (
        await db.execute(
            select(ParsedTransaction).where(
                ParsedTransaction.id == txn_id,
                ParsedTransaction.statement_id == statement.id,
                ParsedTransaction.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parsed transaction not found.")

    llm_response = None
    actions_json = None
    annotation_status = "acknowledged" if request.annotation_type == "comment" else "pending"
    if request.annotation_type == "correction_request":
        result = await run_transaction_correction_chat(
            db=db,
            user_id=user.id,
            message=(
                f"Focus on statement transaction {txn_id}: {parsed.description_raw} "
                f"{float(parsed.amount):.2f} {parsed.direction}. {request.content}"
            ),
            apply_changes=request.apply_changes,
            max_candidates=250,
        )
        llm_response = result.reply
        actions_json = {
            "warnings": result.warnings,
            "actions": result.actions,
            "proposed_count": result.proposed_count,
            "applied_count": result.applied_count,
        }
        annotation_status = "applied" if request.apply_changes and result.applied_count > 0 else "pending"

    annotation = TransactionAnnotation(
        user_id=user.id,
        parsed_transaction_id=parsed.id,
        statement_id=statement.id,
        annotation_type=request.annotation_type,
        content=request.content.strip(),
        llm_response=llm_response,
        status=annotation_status,
        actions_json=actions_json,
        page_number=request.page_number,
    )
    db.add(annotation)
    await db.flush()
    return _to_annotation_response(annotation)


@router.post("/{statement_id}/transactions/{txn_id}/verify", response_model=MessageResponse)
async def verify_statement_transaction(statement_id: str, txn_id: str, user: CurrentUser, db: DbSession):
    parsed = (
        await db.execute(
            select(ParsedTransaction)
            .join(Statement, ParsedTransaction.statement_id == Statement.id)
            .where(
                ParsedTransaction.id == txn_id,
                Statement.id == statement_id,
                Statement.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    parsed.reviewer_user_id = user.id
    parsed.reviewed_at = datetime.now(timezone.utc)
    parsed.is_quarantined = False
    await db.flush()
    return MessageResponse(message="Transaction verified.")


@router.post("/{statement_id}/bulk-verify", response_model=MessageResponse)
async def bulk_verify_statement(statement_id: str, user: CurrentUser, db: DbSession):
    statement = (
        await db.execute(
            select(Statement).where(Statement.id == statement_id, Statement.user_id == user.id)
        )
    ).scalar_one_or_none()
    if statement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    parsed_transactions = (
        await db.execute(
            select(ParsedTransaction).where(
                ParsedTransaction.statement_id == statement.id,
                ParsedTransaction.user_id == user.id,
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for parsed in parsed_transactions:
        parsed.reviewer_user_id = user.id
        parsed.reviewed_at = now
        parsed.is_quarantined = False
    statement.quarantined_row_count = 0
    if statement.parse_status == "review_required":
        statement.parse_status = "parsed"
    await db.flush()
    return MessageResponse(message=f"Verified {len(parsed_transactions)} statement transactions.")


@router.post("/{statement_id}/re-review", response_model=StatementResponse)
async def rereview_statement(statement_id: str, user: CurrentUser, db: DbSession):
    row = (
        await db.execute(
            select(
                Statement,
                RawPdf.id.label("pdf_id"),
                RawPdf.original_filename.label("pdf_filename"),
                RawPdf.source_type.label("source_type"),
            )
            .outerjoin(RawPdf, Statement.pdf_id == RawPdf.id)
            .where(Statement.id == statement_id, Statement.user_id == user.id)
            .limit(1)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    statement, _pdf_id, _pdf_filename, _source_type = row

    try:
        reparsed = await rereview_statement_with_llm(
            db=db,
            user_id=user.id,
            statement=statement,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    raw_pdf = (
        await db.execute(
            select(RawPdf).where(RawPdf.id == reparsed.pdf_id).limit(1)
        )
    ).scalar_one_or_none()
    reprocess_count = 1
    if raw_pdf is not None:
        reprocess_count = (
            await db.execute(
                select(func.count(Statement.id))
                .join(RawPdf, Statement.pdf_id == RawPdf.id)
                .where(
                    Statement.user_id == user.id,
                    RawPdf.file_hash_sha256 == raw_pdf.file_hash_sha256,
                )
            )
        ).scalar() or 1

    return _to_statement_response(
        reparsed,
        str(raw_pdf.id) if raw_pdf else None,
        raw_pdf.original_filename if raw_pdf else None,
        raw_pdf.source_type if raw_pdf else None,
        reprocess_count,
    )


@router.delete("/{statement_id}", response_model=MessageResponse)
async def delete_statement(statement_id: str, user: CurrentUser, db: DbSession):
    statement = (
        await db.execute(
            select(Statement).where(Statement.id == statement_id, Statement.user_id == user.id).limit(1)
        )
    ).scalar_one_or_none()
    if statement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    result = await delete_statement_and_memory(
        db=db,
        user_id=user.id,
        statement=statement,
        remove_pdf=True,
    )
    return MessageResponse(
        message=(
            "Statement deleted. "
            f"Removed {result.deleted_parsed_transactions} parsed transactions, "
            f"{result.deleted_canonical_transactions} canonical transactions, "
            "and the local LLM memory for this PDF."
        )
    )


def _resolve_storage_path(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    if os.path.exists(storage_path):
        return storage_path

    # Backward compatibility for previously containerized paths.
    if storage_path.startswith("/app/uploads/"):
        relative = storage_path.removeprefix("/app/uploads/").lstrip("/")
        candidate = os.path.join(settings.upload_dir, relative)
        if os.path.exists(candidate):
            return candidate
    return storage_path
