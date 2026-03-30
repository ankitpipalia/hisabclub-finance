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
    category_name: str | None = None
    bank_name: str | None
    bank_label: str | None = None
    account_type: str | None
    account_masked: str | None
    is_recurring: bool
    is_anomalous: bool
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


class TransactionSourceResponse(BaseModel):
    source_type: str
    description_raw: str
    confidence: float
    extraction_method: str
    match_method: str
    is_primary: bool


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
