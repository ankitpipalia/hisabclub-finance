from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.merger import promote_to_canonical
from app.models.parsed_transaction import ParsedTransaction
from app.models.review_task import ReviewTask
from app.models.statement import Statement
from app.schemas.review import (
    ResolveReviewTaskRequest,
    ResolveReviewTaskResponse,
    ReviewTaskResponse,
)

router = APIRouter()


def _to_review_task_response(task: ReviewTask) -> ReviewTaskResponse:
    return ReviewTaskResponse(
        id=str(task.id),
        statement_id=str(task.statement_id),
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
        await db.execute(query.order_by(desc(ReviewTask.created_at)).limit(limit))
    ).scalars().all()
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
        await db.execute(
            select(ParsedTransaction)
            .where(
                ParsedTransaction.user_id == user.id,
                ParsedTransaction.statement_id == statement.id,
                ParsedTransaction.is_quarantined == True,  # noqa: E712
            )
            .order_by(ParsedTransaction.transaction_date.asc(), ParsedTransaction.created_at.asc())
        )
    ).scalars().all()

    promoted = 0
    ignored = 0
    now = datetime.now(timezone.utc)
    for parsed in rows:
        parsed.reviewer_user_id = user.id
        parsed.override_reason_code = request.reason_code or ("manual_" + action)
        parsed.reviewed_at = now
        parsed.is_quarantined = False

        if action == "promote":
            await promote_to_canonical(
                db=db,
                user_id=user.id,
                parsed_txn=parsed,
                bank_name=statement.bank_name,
                account_type=statement.account_type,
                account_masked=statement.account_number_masked,
            )
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
        "ignored_count": ignored,
    }

    statement.quarantined_row_count = 0
    statement.promoted_row_count = (statement.promoted_row_count or 0) + promoted
    if action == "promote":
        statement.parse_status = "parsed"
    else:
        statement.parse_status = "partial"

    return ResolveReviewTaskResponse(
        task=_to_review_task_response(task),
        promoted_count=promoted,
        ignored_count=ignored,
    )

