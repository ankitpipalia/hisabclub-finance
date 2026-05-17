from datetime import date, datetime

from pydantic import BaseModel


class TransactionResponse(BaseModel):
    id: str
    transaction_date: date
    posting_date: date | None
    amount: float
    direction: str
    transaction_nature: str
    currency: str
    merchant_raw: str
    merchant_normalized: str | None
    category_id: str | None = None
    category_name: str | None = None
    bank_name: str | None
    bank_label: str | None = None
    account_type: str | None
    account_masked: str | None
    is_recurring: bool
    is_anomalous: bool
    is_excluded: bool
    notes: str | None
    tags: list[str] | None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    per_page: int


class TransactionUpdateRequest(BaseModel):
    category_id: str | None = None
    merchant_id: str | None = None
    transaction_nature: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    is_excluded: bool | None = None


class TransactionBulkUpdateRequest(TransactionUpdateRequest):
    transaction_ids: list[str]


class TransactionBulkUpdateResponse(BaseModel):
    updated_count: int
    items: list[TransactionResponse]


class TransactionSplitPartRequest(BaseModel):
    amount: float
    merchant_raw: str | None = None
    category_id: str | None = None
    merchant_id: str | None = None
    transaction_nature: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class TransactionSplitRequest(BaseModel):
    parts: list[TransactionSplitPartRequest]
    exclude_original: bool = True


class TransactionSplitResponse(BaseModel):
    original_transaction: TransactionResponse
    created_transactions: list[TransactionResponse]


class TransactionSourceResponse(BaseModel):
    parsed_txn_id: str
    statement_id: str | None = None
    source_type: str
    description_raw: str
    confidence: float
    extraction_method: str
    match_method: str
    is_primary: bool


class TransactionOverrideResponse(BaseModel):
    id: str
    field_name: str
    old_value: str | None
    new_value: str
    override_reason: str | None
    created_at: datetime


class TransactionDetailResponse(BaseModel):
    transaction: TransactionResponse
    sources: list[TransactionSourceResponse]
    overrides: list[TransactionOverrideResponse]
    split_parent: TransactionResponse | None = None
    split_children: list[TransactionResponse]


class AutoCategorizeResponse(BaseModel):
    scanned: int
    updated: int


class ReclassifyTransferResponse(BaseModel):
    scanned: int
    updated: int
    matched_credit_card_pairs: int
    llm_checked: int
    llm_promoted: int


class UpiReconcileResponse(BaseModel):
    scanned: int
    matched_pairs: int
    updated_transactions: int


class TransactionSearchHit(BaseModel):
    transaction_id: str
    transaction_date: str
    amount: str
    direction: str
    merchant: str
    category_name: str | None = None
    bank_name: str | None = None
    account_masked: str | None = None
    score: float
    matched_terms: list[str]


class TransactionSearchResponse(BaseModel):
    query: str
    items: list[TransactionSearchHit]
    total: int
