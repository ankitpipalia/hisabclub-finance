from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationThreadResponse(BaseModel):
    id: str
    statement_id: str | None = None
    title: str
    status: str
    summary: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime
    pending_question_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ConversationMessageResponse(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    message_index: int
    metadata_json: dict | None = None
    is_applied: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationReplyRequest(BaseModel):
    message: str
    apply_changes: bool = False


class ConversationCreateRequest(BaseModel):
    title: str
    statement_id: str | None = None
    initial_message: str | None = None


class ConversationReplyResponse(BaseModel):
    thread: ConversationThreadResponse
    message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse
    warnings: list[str] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    proposed_count: int = 0
    applied_count: int = 0
    skipped_count: int = 0


class ConversationResolveResponse(BaseModel):
    thread: ConversationThreadResponse
    resolved: bool


class ConversationPendingCountResponse(BaseModel):
    pending_count: int
