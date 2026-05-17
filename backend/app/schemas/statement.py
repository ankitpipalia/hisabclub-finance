from datetime import date, datetime

from pydantic import BaseModel


class StatementResponse(BaseModel):
    id: str
    pdf_id: str | None = None
    pdf_filename: str | None = None
    bank_name: str
    account_type: str
    account_number_masked: str | None
    statement_period_start: date | None
    statement_period_end: date | None
    due_date: date | None
    min_amount_due: float | None
    total_amount_due: float | None
    credit_limit: float | None
    opening_balance: float | None
    closing_balance: float | None
    parser_used: str
    parse_status: str
    transaction_count: int | None
    expected_row_count: int | None = None
    extracted_row_count: int | None = None
    promoted_row_count: int | None = None
    quarantined_row_count: int | None = None
    yield_rate: float | None = None
    balance_walk_passed: bool | None = None
    balance_walk_delta: float | None = None
    total_extracted: int = 0
    total_promoted: int = 0
    total_duplicates: int = 0
    total_in_review: int = 0
    source_type: str | None = None
    is_reprocess: bool = False
    reprocess_count: int = 1
    created_at: datetime

    class Config:
        from_attributes = True


class StatementListResponse(BaseModel):
    items: list[StatementResponse]
    total: int


class StatementIntegrityResponse(BaseModel):
    statement_id: str
    account_type: str
    status: str
    transaction_count: int
    debit_total: float
    credit_total: float
    net_activity: float
    total_amount_due: float | None
    min_amount_due: float | None
    previous_balance: float | None
    closing_balance: float | None
    expected_closing_balance: float | None
    due_gap: float | None
    closing_balance_gap: float | None
    tolerance_due: float
    tolerance_balance: float
    llm_status: str | None
    llm_confidence: float | None
    llm_reason: str | None
    notes: list[str]


class StatementAnnotationResponse(BaseModel):
    id: str
    parsed_transaction_id: str | None = None
    canonical_transaction_id: str | None = None
    statement_id: str
    annotation_type: str
    content: str
    llm_response: str | None = None
    status: str
    actions_json: dict | None = None
    page_number: int | None = None
    created_at: datetime
    updated_at: datetime


class StatementReviewTransactionResponse(BaseModel):
    id: str
    canonical_transaction_id: str | None = None
    transaction_date: date
    posting_date: date | None = None
    description_raw: str
    amount: float
    direction: str
    confidence: float
    is_quarantined: bool
    extraction_method: str
    line_number: int | None = None
    page_number: int | None = None
    reviewer_user_id: str | None = None
    reviewed_at: datetime | None = None
    annotations: list[StatementAnnotationResponse] = []


class StatementReviewResponse(BaseModel):
    statement: StatementResponse
    transactions: list[StatementReviewTransactionResponse]
    annotations: list[StatementAnnotationResponse]


class StatementAnnotationRequest(BaseModel):
    annotation_type: str
    content: str
    page_number: int | None = None
    apply_changes: bool = False
