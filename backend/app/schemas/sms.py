from datetime import datetime

from pydantic import BaseModel


class SmsBatchItemRequest(BaseModel):
    sms_hash: str
    sender_address: str
    sender_id: str | None = None
    body: str
    sms_timestamp: datetime
    classification: str | None = None
    bank_name: str | None = None
    account_type: str | None = None
    account_masked: str | None = None
    direction: str | None = None
    amount: float | None = None
    description: str | None = None
    reference_number: str | None = None
    upi_id: str | None = None
    confidence: float = 1.0


class SmsBatchRequest(BaseModel):
    device_id: str | None = None
    items: list[SmsBatchItemRequest]


class SmsBatchItemResult(BaseModel):
    sms_hash: str
    status: str  # "accepted" | "duplicate" | "error"
    transaction_id: str | None = None
    error: str | None = None


class SmsBatchResponse(BaseModel):
    accepted: int
    duplicates: int
    errors: int
    details: list[SmsBatchItemResult]
