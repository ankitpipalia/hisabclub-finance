from datetime import datetime

from pydantic import BaseModel


class UploadResponse(BaseModel):
    pdf_id: str
    document_id: str | None = None
    status: str
    message: str
    bank_name: str | None = None
    account_type: str | None = None
    parser_used: str | None = None


class UploadStatusResponse(BaseModel):
    pdf_id: str
    document_id: str | None = None
    status: str
    message: str | None = None
    statement_id: str | None = None
    transaction_count: int | None = None
    error: str | None = None
    bank_name: str | None = None


class UploadReviewItemResponse(BaseModel):
    pdf_id: str
    document_id: str | None = None
    file_name: str
    status: str
    message: str
    bank_name: str | None = None
    account_type: str | None = None
    parser_used: str | None = None
    transaction_count: int | None = None
    created_at: str | None = None


class ExtractionJobResponse(BaseModel):
    id: str
    document_id: str
    status: str
    current_stage: str | None = None
    attempt_count: int
    max_attempts: int
    dlq_retry_count: int
    error_code: str | None = None
    error_message: str | None = None
    statement_id: str | None = None
    created_at: datetime
    next_run_at: datetime
    finished_at: datetime | None = None


class ParserHealthItemResponse(BaseModel):
    bank_code: str
    account_type: str
    parser_id: str | None = None
    observed_success_count: int
    observed_failure_count: int
    observed_expected_rows: int = 0
    observed_extracted_rows: int = 0
    success_rate: float
    yield_rate: float | None = None


class BulkUploadResultItem(BaseModel):
    file_name: str
    pdf_id: str
    document_id: str | None = None
    status: str
    message: str
    bank_name: str | None = None
    account_type: str | None = None


class BulkUploadResponse(BaseModel):
    total: int
    success_count: int
    reviewing_count: int
    duplicate_count: int
    failed_count: int
    items: list[BulkUploadResultItem]
