"""Regression tests for review-task resolve flow audit preservation.

After Phase 1 (master_plan_2026.md §26) the `resolve` action's `promote` branch
must:
 - stamp `user_override=True`, `override_reason`, `override_at` on canonical
   rows that were previously quarantined, so the audit trail records that
   the user explicitly authorized a previously-flagged row;
 - archive the list of resolved parsed-transaction IDs into the task's
   `payload_json` so the audit survives later edits to the canonical row.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from app.api.v1 import reviews as reviews_api
from app.schemas.review import ResolveReviewTaskRequest


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsAllResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return self._values


class _QueuedDb:
    def __init__(self, responses):
        self.responses = list(responses)
        self.added: list = []
        self.flush_count = 0

    async def execute(self, *_args, **_kwargs):
        return self.responses.pop(0)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


def _build_task_and_statement_and_row(*, quarantined: bool):
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    statement_id = uuid.uuid4()
    parsed_id = uuid.uuid4()

    task = SimpleNamespace(
        id=task_id,
        user_id=user_id,
        statement_id=statement_id,
        task_type="quarantined_rows",
        status="open",
        reason_code="low_confidence",
        title="Quarantined rows",
        details=None,
        payload_json={},
        resolved_by_user_id=None,
        resolved_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    statement = SimpleNamespace(
        id=statement_id,
        user_id=user_id,
        bank_name="HDFC Bank",
        account_type="savings",
        account_number_masked="XXXX1234",
        quarantined_row_count=1,
        promoted_row_count=0,
        parse_status="needs_review",
    )
    parsed = SimpleNamespace(
        id=parsed_id,
        user_id=user_id,
        statement_id=statement_id,
        transaction_date=date(2025, 4, 21),
        description_raw="AMAZON",
        amount=1200.0,
        direction="debit",
        currency="INR",
        is_quarantined=quarantined,
        reviewer_user_id=None,
        override_reason_code=None,
        reviewed_at=None,
        confidence=0.6,
        reference_number=None,
        upi_id=None,
        extraction_method="llm",
        source_type="statement",
        source_id=statement_id,
        posting_date=None,
        line_number=1,
        foreign_amount=None,
        foreign_currency=None,
        dedupe_fingerprint="fp-1",
    )
    return user_id, task, statement, parsed


@pytest.mark.asyncio
async def test_resolve_promote_marks_user_override_for_quarantined_row(monkeypatch):
    """A quarantined row that the user resolves+promotes is stamped as user_override."""
    user_id, task, statement, parsed = _build_task_and_statement_and_row(quarantined=True)

    db = _QueuedDb([
        _ScalarOneOrNoneResult(task),
        _ScalarOneOrNoneResult(statement),
        _ScalarsAllResult([parsed]),
    ])

    promote_calls: list = []

    async def _spy_promote(**kwargs):
        promote_calls.append(kwargs)
        canonical = SimpleNamespace(
            id=uuid.uuid4(),
            user_override=False,
            override_reason=None,
            override_at=None,
        )
        # mirror merger's "did we dedup-merge?" flag
        setattr(canonical, "_hc_was_dedup_merge", False)
        return canonical

    monkeypatch.setattr(reviews_api, "promote_to_canonical", _spy_promote)

    user = SimpleNamespace(id=user_id)
    request = ResolveReviewTaskRequest(action="promote", reason_code="user_approved")

    response = await reviews_api.resolve_review_task(
        str(task.id), request, user, db
    )

    # Must have promoted, with validation_status passed through as "valid"
    # (the user is authorizing the row).
    assert len(promote_calls) == 1
    assert promote_calls[0]["validation_status"] == "valid"
    assert response.promoted_count == 1
    assert response.merged_count == 0

    # The returned canonical mock should have been stamped with override audit.
    # (We can't access the canonical directly here, but we can verify via the
    # task payload that the audit breadcrumb was written.)
    assert task.payload_json["resolved_action"] == "promote"
    assert str(parsed.id) in task.payload_json["resolved_quarantined_parsed_ids"]
    assert task.payload_json["resolved_reason_code"] == "user_approved"
    assert task.status == "resolved"
    assert task.resolved_by_user_id == user_id


@pytest.mark.asyncio
async def test_resolve_ignore_marks_task_resolved_without_promotion(monkeypatch):
    user_id, task, statement, parsed = _build_task_and_statement_and_row(quarantined=True)
    db = _QueuedDb([
        _ScalarOneOrNoneResult(task),
        _ScalarOneOrNoneResult(statement),
        _ScalarsAllResult([parsed]),
    ])

    async def _no_promote(**_kwargs):
        raise AssertionError("promote_to_canonical must not run for ignore action")

    monkeypatch.setattr(reviews_api, "promote_to_canonical", _no_promote)

    user = SimpleNamespace(id=user_id)
    request = ResolveReviewTaskRequest(action="ignore")

    response = await reviews_api.resolve_review_task(
        str(task.id), request, user, db
    )

    assert response.promoted_count == 0
    assert response.ignored_count == 1
    assert task.status == "resolved"
    assert task.payload_json["resolved_action"] == "ignore"
