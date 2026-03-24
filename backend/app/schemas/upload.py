from pydantic import BaseModel


class UploadResponse(BaseModel):
    pdf_id: str
    status: str
    message: str


class UploadStatusResponse(BaseModel):
    pdf_id: str
    status: str
    statement_id: str | None = None
    transaction_count: int | None = None
    error: str | None = None
    bank_name: str | None = None
