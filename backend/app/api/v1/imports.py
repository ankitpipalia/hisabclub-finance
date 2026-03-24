import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.intake.folder_importer import import_folder
from app.engines.ledger.nature import infer_transaction_nature
from app.models.canonical_transaction import CanonicalTransaction
from app.models.document_artifact import DocumentArtifact
from app.schemas.imports import (
    FolderImportRequest,
    FolderImportResponse,
    ParserSupportQueueItem,
    ParserSupportQueueResponse,
)

router = APIRouter()


@router.post("/folder", response_model=FolderImportResponse)
async def import_local_folder(
    request: FolderImportRequest,
    user: CurrentUser,
    db: DbSession,
):
    try:
        result = await import_folder(
            db=db,
            user_id=user.id,
            folder_path=request.folder_path,
            parse_supported=request.parse_supported,
            dry_run=request.dry_run,
            force_reprocess=request.force_reprocess,
            password_map=request.password_map,
            max_files=request.max_files,
        )
        await db.commit()
        return FolderImportResponse(
            discovered=result.discovered,
            ingested=result.ingested,
            parsed=result.parsed,
            skipped=result.skipped,
            failed=result.failed,
            by_doc_type=result.by_doc_type,
            messages=result.messages,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/artifacts")
async def list_document_artifacts(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    doc_type: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    query = (
        select(DocumentArtifact)
        .where(DocumentArtifact.user_id == user.id)
        .order_by(DocumentArtifact.discovered_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(DocumentArtifact.status == status_filter)
    if doc_type:
        query = query.where(DocumentArtifact.doc_type == doc_type)

    rows = (await db.execute(query)).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "file_path": r.file_path,
                "file_name": r.file_name,
                "file_ext": r.file_ext,
                "doc_type": r.doc_type,
                "doc_subtype": r.doc_subtype,
                "bank_hint": r.bank_hint,
                "status": r.status,
                "parse_message": r.parse_message,
                "discovered_at": r.discovered_at,
                "processed_at": r.processed_at,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/artifacts/{artifact_id}/file")
async def get_document_artifact_file(
    artifact_id: str,
    user: CurrentUser,
    db: DbSession,
):
    artifact = (
        await db.execute(
            select(DocumentArtifact).where(
                DocumentArtifact.id == artifact_id,
                DocumentArtifact.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found.",
        )

    file_path = artifact.file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact file is missing on disk.",
        )

    _validate_artifact_path_allowed(Path(file_path).expanduser().resolve())

    media_type = (
        "application/pdf"
        if artifact.file_ext.lower() == "pdf"
        else "application/octet-stream"
    )
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=artifact.file_name,
        headers={"Content-Disposition": f'inline; filename="{artifact.file_name}"'},
    )


@router.get("/parser-support-queue", response_model=ParserSupportQueueResponse)
async def parser_support_queue(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(500, ge=1, le=5000),
):
    query = (
        select(DocumentArtifact)
        .where(DocumentArtifact.user_id == user.id)
        .where(DocumentArtifact.doc_type.in_(("bank_statement", "credit_card_statement")))
        .where(
            (DocumentArtifact.status == "failed")
            | (
                (DocumentArtifact.status == "skipped")
                & (
                    DocumentArtifact.parse_message.ilike("%No parser configured%")
                    | DocumentArtifact.parse_message.ilike(
                        "%Could not identify the bank/statement type%"
                    )
                )
            )
        )
        .order_by(DocumentArtifact.discovered_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).scalars().all()

    grouped: dict[tuple[str | None, str, str], dict] = {}
    for row in rows:
        reason = _queue_reason(row.parse_message or "")
        key = (row.bank_hint, row.doc_type, reason)
        item = grouped.setdefault(
            key,
            {
                "bank_hint": row.bank_hint,
                "doc_type": row.doc_type,
                "reason": reason,
                "count": 0,
                "sample_files": [],
                "sample_message": row.parse_message,
                "last_seen": row.discovered_at,
            },
        )
        item["count"] += 1
        if row.file_name not in item["sample_files"] and len(item["sample_files"]) < 5:
            item["sample_files"].append(row.file_name)
        if row.discovered_at and (
            item["last_seen"] is None or row.discovered_at > item["last_seen"]
        ):
            item["last_seen"] = row.discovered_at

    items = [ParserSupportQueueItem(**payload) for payload in grouped.values()]
    items.sort(key=lambda x: (-x.count, x.doc_type, x.bank_hint or ""))
    return ParserSupportQueueResponse(total=len(items), items=items)


@router.post("/reclassify-nature")
async def reclassify_transaction_natures(user: CurrentUser, db: DbSession):
    rows = (
        await db.execute(
            select(CanonicalTransaction).where(CanonicalTransaction.user_id == user.id)
        )
    ).scalars().all()

    updated = 0
    for txn in rows:
        inferred = infer_transaction_nature(
            description_raw=txn.merchant_raw,
            direction=txn.direction,
            account_type=txn.account_type,
        )
        if inferred != txn.transaction_nature:
            txn.transaction_nature = inferred
            updated += 1

    await db.commit()
    return {"total": len(rows), "updated": updated}


def _queue_reason(parse_message: str) -> str:
    msg = parse_message.lower()
    if "no parser configured" in msg:
        return "unsupported_bank"
    if "could not identify the bank/statement type" in msg:
        return "unknown_format"
    if "password-protected" in msg:
        return "password_required"
    return "parse_error"


def _validate_artifact_path_allowed(path: Path) -> None:
    if not settings.local_only_mode:
        return
    allowed_roots = [Path(p).expanduser().resolve() for p in settings.parsed_local_roots()]
    if any(path.is_relative_to(root) for root in allowed_roots):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Artifact path is outside configured local roots.",
    )
