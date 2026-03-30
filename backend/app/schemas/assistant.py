from pydantic import BaseModel, Field


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=4000)
    apply_changes: bool = True
    max_candidates: int = Field(default=80, ge=20, le=400)


class AssistantActionResult(BaseModel):
    action: str
    transaction_id: str
    status: str
    detail: str
    before: str | None = None
    after: str | None = None


class AssistantChatResponse(BaseModel):
    reply: str
    proposed_count: int
    applied_count: int
    skipped_count: int
    warnings: list[str]
    actions: list[AssistantActionResult]
