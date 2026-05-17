from datetime import datetime

from pydantic import BaseModel


class ReviewTaskResponse(BaseModel):
    id: str
    statement_id: str | None
    task_type: str
    status: str
    reason_code: str
    title: str
    details: str | None = None
    payload_json: dict | None = None
    resolved_by_user_id: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResolveReviewTaskRequest(BaseModel):
    action: str  # promote | ignore
    reason_code: str | None = None


class ResolveReviewTaskResponse(BaseModel):
    task: ReviewTaskResponse
    promoted_count: int
    ignored_count: int
    merged_count: int = 0


class CorrectReviewTaskRequest(BaseModel):
    corrections: dict
    reason: str | None = None
