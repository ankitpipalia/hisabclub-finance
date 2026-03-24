import os

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.insights.statement_integrity import build_credit_card_statement_integrity
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.schemas.statement import (
    StatementIntegrityResponse,
    StatementListResponse,
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
        source_type=source_type,
        is_reprocess=is_reprocess,
        reprocess_count=safe_reprocess_count,
        created_at=statement.created_at,
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
        .where(Statement.user_id == user.id)
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
