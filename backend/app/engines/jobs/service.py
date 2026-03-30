from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.jobs.notifier import publish_job_event
from app.models.extraction_job import ExtractionJob


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_parse_job(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    raw_pdf_id: uuid.UUID,
    payload: dict | None = None,
    priority: int = 100,
) -> ExtractionJob:
    job = ExtractionJob(
        user_id=user_id,
        raw_pdf_id=raw_pdf_id,
        job_type="parse_statement",
        status="queued",
        current_stage="queued",
        priority=priority,
        payload_json=payload or {},
    )
    db.add(job)
    await db.flush()
    await publish_job_event(
        "job.queued",
        {
            "job_id": str(job.id),
            "user_id": str(user_id),
            "raw_pdf_id": str(raw_pdf_id),
        },
    )
    return job


async def claim_next_job(
    *,
    db: AsyncSession,
    worker_id: str,
) -> ExtractionJob | None:
    now = _utcnow()
    queued_by_user = (
        select(
            ExtractionJob.user_id.label("user_id"),
            func.min(ExtractionJob.created_at).label("oldest_created_at"),
        )
        .where(
            ExtractionJob.status == "queued",
            ExtractionJob.next_run_at <= now,
        )
        .group_by(ExtractionJob.user_id)
        .subquery()
    )
    running_by_user = (
        select(
            ExtractionJob.user_id.label("user_id"),
            func.count(ExtractionJob.id).label("running_count"),
        )
        .where(ExtractionJob.status == "running")
        .group_by(ExtractionJob.user_id)
        .subquery()
    )
    selected_user = (
        await db.execute(
            select(queued_by_user.c.user_id)
            .select_from(
                queued_by_user.outerjoin(
                    running_by_user,
                    queued_by_user.c.user_id == running_by_user.c.user_id,
                )
            )
            .order_by(
                func.coalesce(running_by_user.c.running_count, 0).asc(),
                queued_by_user.c.oldest_created_at.asc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if selected_user is None:
        return None

    row = (
        await db.execute(
            select(ExtractionJob)
            .where(
                ExtractionJob.status == "queued",
                ExtractionJob.next_run_at <= now,
                ExtractionJob.user_id == selected_user,
            )
            .order_by(ExtractionJob.priority.desc(), asc(ExtractionJob.created_at))
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = (
            await db.execute(
                select(ExtractionJob)
                .where(
                    ExtractionJob.status == "queued",
                    ExtractionJob.next_run_at <= now,
                )
                .order_by(ExtractionJob.priority.desc(), asc(ExtractionJob.created_at))
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None

    row.status = "running"
    row.current_stage = "extracting"
    row.locked_by = worker_id
    row.locked_at = now
    if row.started_at is None:
        row.started_at = now
    row.attempt_count += 1
    await db.flush()
    await publish_job_event(
        "job.running",
        {"job_id": str(row.id), "worker_id": worker_id, "attempt_count": row.attempt_count},
    )
    return row


async def complete_job(
    *,
    db: AsyncSession,
    job: ExtractionJob,
    statement_id: uuid.UUID | None,
    result: dict,
) -> None:
    now = _utcnow()
    job.status = "completed"
    job.current_stage = "completed"
    job.statement_id = statement_id
    job.result_json = result
    job.finished_at = now
    job.error_code = None
    job.error_message = None
    job.locked_at = None
    job.locked_by = None
    await db.flush()
    await publish_job_event(
        "job.completed",
        {"job_id": str(job.id), "statement_id": str(statement_id) if statement_id else None},
    )


async def fail_or_retry_job(
    *,
    db: AsyncSession,
    job: ExtractionJob,
    error_code: str,
    error_message: str,
    dlq_reason: str | None = None,
) -> None:
    now = _utcnow()
    should_retry = job.attempt_count < job.max_attempts
    if should_retry:
        backoff_sec = min(300, 2 ** max(1, job.attempt_count))
        job.status = "queued"
        job.current_stage = "retry_scheduled"
        job.next_run_at = now + timedelta(seconds=backoff_sec)
    else:
        job.status = "dlq"
        job.current_stage = "dlq"
        job.finished_at = now
        job.dlq_reason = dlq_reason or "max_attempts_exceeded"

    job.error_code = error_code[:50]
    job.error_message = (error_message or "")[:1000]
    job.locked_at = None
    job.locked_by = None
    await db.flush()
    await publish_job_event(
        "job.dlq" if job.status == "dlq" else "job.retry_scheduled",
        {
            "job_id": str(job.id),
            "error_code": job.error_code,
            "attempt_count": job.attempt_count,
            "status": job.status,
        },
    )


async def list_dlq_jobs(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 100,
) -> list[ExtractionJob]:
    rows = (
        await db.execute(
            select(ExtractionJob)
            .where(ExtractionJob.user_id == user_id, ExtractionJob.status == "dlq")
            .order_by(ExtractionJob.finished_at.desc(), ExtractionJob.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return rows


async def requeue_dlq_job(
    *,
    db: AsyncSession,
    job: ExtractionJob,
) -> ExtractionJob:
    now = _utcnow()
    job.status = "queued"
    job.current_stage = "queued"
    job.next_run_at = now
    job.error_code = None
    job.error_message = None
    job.dlq_reason = None
    job.dlq_retry_count += 1
    await db.flush()
    await publish_job_event("job.requeued", {"job_id": str(job.id)})
    return job
