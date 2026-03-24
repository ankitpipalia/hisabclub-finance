from datetime import datetime

from pydantic import BaseModel, Field


class FolderImportRequest(BaseModel):
    folder_path: str = Field(..., description="Absolute local path to scan recursively")
    parse_supported: bool = True
    dry_run: bool = False
    force_reprocess: bool = False
    max_files: int | None = Field(default=None, ge=1, le=5000)
    password_map: dict[str, str] | None = None


class FolderImportResponse(BaseModel):
    discovered: int
    ingested: int
    parsed: int
    skipped: int
    failed: int
    by_doc_type: dict[str, int]
    messages: list[str]


class ParserSupportQueueItem(BaseModel):
    bank_hint: str | None = None
    doc_type: str
    reason: str
    count: int
    sample_files: list[str]
    sample_message: str | None = None
    last_seen: datetime | None = None


class ParserSupportQueueResponse(BaseModel):
    total: int
    items: list[ParserSupportQueueItem]
