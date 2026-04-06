from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.insights import TaxComplianceResponse


class TaxPortalDataResponse(BaseModel):
    id: str
    document_artifact_id: str | None = None
    document_type: str
    assessment_year: str | None = None
    financial_year: str | None = None
    source_name: str | None = None
    pan_masked: str | None = None
    document_date: date | None = None
    extracted_json: dict = Field(default_factory=dict)
    verification_json: dict | None = None
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TaxVerificationCheck(BaseModel):
    check: str
    status: str
    app_amount: float
    portal_amount: float
    gap: float
    detail: str


class TaxVerificationResponse(BaseModel):
    financial_year: str
    tax_report: TaxComplianceResponse
    portal_data: list[TaxPortalDataResponse] = Field(default_factory=list)
    checks: list[TaxVerificationCheck] = Field(default_factory=list)
    discrepancies: list[TaxVerificationCheck] = Field(default_factory=list)


class TaxPortalUploadResponse(BaseModel):
    artifact_id: str
    portal_data_id: str
    document_type: str
    financial_year: str | None = None
    message: str

