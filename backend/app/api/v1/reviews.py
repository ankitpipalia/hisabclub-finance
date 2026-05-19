from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.merger import promote_to_canonical
from app.models.canonical_transaction import CanonicalTransaction
from app.models.parsed_transaction import ParsedTransaction
from app.models.review_task import ReviewTask
from app.models.statement import Statement
from app.schemas.review import (
    CorrectReviewTaskRequest,
    ResolveReviewTaskRequest,
    ResolveReviewTaskResponse,
    ReviewTaskResponse,
)

router = APIRouter()

IMMUTABLE_TRANSACTION_FIELDS = {
    "id",
    "user_id",
    "dedup_key",
    "dedupe_fingerprint",
    "source_statement_id",
    "source_evidence",
    "source_page_number",
    "source_char_offset",
    "extraction_source",
    "created_at",
    "updated_at",
}


def _to_review_task_response(task: ReviewTask) -> ReviewTaskResponse:
    return ReviewTaskResponse(
        id=str(task.id),
        statement_id=str(task.statement_id) if task.statement_id else None,
        task_type=task.task_type,
        status=task.status,
        reason_code=task.reason_code,
        title=task.title,
        details=task.details,
        payload_json=task.payload_json,
        resolved_by_user_id=str(task.resolved_by_user_id) if task.resolved_by_user_id else None,
        resolved_at=task.resolved_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/tasks", response_model=list[ReviewTaskResponse])
async def list_review_tasks(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(ReviewTask).where(ReviewTask.user_id == user.id)
    if status_filter:
        query = query.where(ReviewTask.status == status_filter)
    tasks = (
        (await db.execute(query.order_by(desc(ReviewTask.created_at)).limit(limit))).scalars().all()
    )
    return [_to_review_task_response(task) for task in tasks]


@router.post("/tasks/{task_id}/resolve", response_model=ResolveReviewTaskResponse)
async def resolve_review_task(
    task_id: str,
    request: ResolveReviewTaskRequest,
    user: CurrentUser,
    db: DbSession,
):
    task = (
        await db.execute(
            select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.user_id == user.id)
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if task.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only open review tasks can be resolved.",
        )

    action = (request.action or "").strip().lower()
    if action not in {"promote", "ignore"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action must be one of: promote, ignore",
        )

    if task.statement_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This review task is not linked to a statement.",
        )
    statement = (
        await db.execute(
            select(Statement).where(Statement.id == task.statement_id, Statement.user_id == user.id)
        )
    ).scalar_one_or_none()
    if statement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Related statement not found.",
        )

    rows = (
        (
            await db.execute(
                select(ParsedTransaction)
                .where(
                    ParsedTransaction.user_id == user.id,
                    ParsedTransaction.statement_id == statement.id,
                    ParsedTransaction.is_quarantined == True,  # noqa: E712
                )
                .order_by(
                    ParsedTransaction.transaction_date.asc(), ParsedTransaction.created_at.asc()
                )
            )
        )
        .scalars()
        .all()
    )

    promoted = 0
    merged = 0
    ignored = 0
    now = datetime.now(timezone.utc)
    override_reason_text = (
        request.reason_code
        and f"user-resolved quarantined row via review: {request.reason_code}"
    ) or "user-resolved quarantined row via review"
    for parsed in rows:
        was_quarantined = bool(parsed.is_quarantined)
        parsed.reviewer_user_id = user.id
        parsed.override_reason_code = request.reason_code or ("manual_" + action)
        parsed.reviewed_at = now
        parsed.is_quarantined = False

        if action == "promote":
            # The user explicitly authorized this row. We keep
            # `validation_status="valid"` because the human is the higher
            # authority, but we stamp the canonical with `user_override` so
            # the audit trail records that this row was previously flagged.
            # The prior-validation snapshot is also archived in the review
            # task payload below so it survives even if the canonical is
            # later edited.
            canonical = await promote_to_canonical(
                db=db,
                user_id=user.id,
                parsed_txn=parsed,
                bank_name=statement.bank_name,
                account_type=statement.account_type,
                account_masked=statement.account_number_masked,
                validation_status="valid",
                validation_errors=None,
            )
            if was_quarantined:
                canonical.user_override = True
                canonical.override_reason = override_reason_text
                canonical.override_at = now
            if getattr(canonical, "_hc_was_dedup_merge", False):
                merged += 1
            else:
                promoted += 1
        else:
            ignored += 1

    task.status = "resolved"
    task.resolved_by_user_id = user.id
    task.resolved_at = now
    task.payload_json = {
        **(task.payload_json or {}),
        "resolved_action": action,
        "promoted_count": promoted,
        "merged_count": merged,
        "ignored_count": ignored,
        # Audit-trail breadcrumb: capture which parsed rows were quarantined
        # at the moment the user resolved them. This survives later edits to
        # the resulting canonical and lets the UI/Assistant show "this row
        # was previously flagged and then approved by user".
        "resolved_quarantined_parsed_ids": [
            str(row.id) for row in rows if hasattr(row, "id")
        ],
        "resolved_reason_code": request.reason_code,
    }

    statement.quarantined_row_count = 0
    statement.promoted_row_count = (statement.promoted_row_count or 0) + promoted
    if action == "promote":
        statement.parse_status = "parsed"
    else:
        statement.parse_status = "partial"

    await db.flush()

    return ResolveReviewTaskResponse(
        task=_to_review_task_response(task),
        promoted_count=promoted,
        ignored_count=ignored,
        merged_count=merged,
    )


@router.post("/tasks/{task_id}/approve", response_model=ReviewTaskResponse)
async def approve_review_task(task_id: str, user: CurrentUser, db: DbSession):
    task = await _get_open_task(task_id=task_id, user_id=user.id, db=db)
    txn = await _canonical_from_task(task=task, user_id=user.id, db=db)
    now = datetime.now(timezone.utc)
    if txn is not None:
        txn.review_task_id = None
        _archive_prior_validation(task, txn)
        txn.validation_status = "valid"
    task.status = "resolved"
    task.resolved_by_user_id = user.id
    task.resolved_at = now
    task.payload_json = {**(task.payload_json or {}), "resolved_action": "approved"}
    return _to_review_task_response(task)


@router.post("/tasks/{task_id}/correct", response_model=ReviewTaskResponse)
async def correct_review_task(
    task_id: str,
    request: CorrectReviewTaskRequest,
    user: CurrentUser,
    db: DbSession,
):
    task = await _get_open_task(task_id=task_id, user_id=user.id, db=db)
    txn = await _canonical_from_task(task=task, user_id=user.id, db=db)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review task is not linked to a canonical transaction.",
        )

    applied: dict[str, str] = {}
    for field, value in (request.corrections or {}).items():
        if field in IMMUTABLE_TRANSACTION_FIELDS or not hasattr(txn, field):
            continue
        coerced = _coerce_transaction_value(field, value)
        setattr(txn, field, coerced)
        applied[field] = str(coerced)

    now = datetime.now(timezone.utc)
    txn.user_override = True
    txn.override_reason = request.reason
    txn.override_at = now
    txn.review_task_id = None
    _archive_prior_validation(task, txn)
    txn.validation_status = "valid"
    task.status = "resolved"
    task.resolved_by_user_id = user.id
    task.resolved_at = now
    task.payload_json = {
        **(task.payload_json or {}),
        "resolved_action": "corrected",
        "applied_corrections": applied,
        "correction_reason": request.reason,
    }
    return _to_review_task_response(task)


def _archive_prior_validation(task: ReviewTask, txn: CanonicalTransaction) -> None:
    payload = dict(task.payload_json or {})
    payload.setdefault(
        "prior_validation",
        {
            "status": txn.validation_status,
            "errors": txn.validation_errors,
        },
    )
    task.payload_json = payload


async def _get_open_task(*, task_id: str, user_id, db: DbSession) -> ReviewTask:
    task = (
        await db.execute(
            select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.user_id == user_id)
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if task.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only open review tasks can be changed.",
        )
    return task


async def _canonical_from_task(
    *, task: ReviewTask, user_id, db: DbSession
) -> CanonicalTransaction | None:
    payload = task.payload_json or {}
    txn_id = payload.get("canonical_transaction_id")
    if not txn_id:
        return None
    return (
        await db.execute(
            select(CanonicalTransaction).where(
                CanonicalTransaction.id == txn_id,
                CanonicalTransaction.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def _coerce_transaction_value(field: str, value):
    if field in {"amount", "foreign_amount"}:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid decimal for {field}") from exc
    if field in {"transaction_date", "posting_date"}:
        if value in {None, ""} and field == "posting_date":
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date for {field}") from exc
    if field in {"is_recurring", "is_anomalous", "is_excluded"}:
        return bool(value)
    return value
