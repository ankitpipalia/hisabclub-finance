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


class TaxPlanningSectionResponse(BaseModel):
    section: str
    label: str
    ytd_amount: str
    limit: str
    remaining: str | None = None
    progress_pct: float | None = None


class TaxPlanningResponse(BaseModel):
    financial_year: str
    sections: list[TaxPlanningSectionResponse] = Field(default_factory=list)


# -------- Phase 2 (master_plan_2026.md): regime + ITR + what-if -------- #


class RegimeInputs(BaseModel):
    """Inputs for /tax/regime/compare. All money fields are ₹ as strings to
    preserve Decimal precision over the wire."""

    gross_salary: str = "0"
    interest_income: str = "0"
    dividend_income: str = "0"
    rental_income_net: str = "0"
    other_income: str = "0"
    capital_gain_equity_stcg: str = "0"
    capital_gain_equity_ltcg: str = "0"
    capital_gain_other: str = "0"
    deduction_80c: str = "0"
    deduction_80ccd_1b: str = "0"
    deduction_80ccd_2: str = "0"
    deduction_80d_self: str = "0"
    deduction_80d_parents: str = "0"
    deduction_80e: str = "0"
    deduction_80g: str = "0"
    deduction_80gg: str = "0"
    deduction_80tta_or_ttb: str = "0"
    home_loan_interest_self: str = "0"
    home_loan_interest_letout: str = "0"
    is_salaried: bool = True
    is_pensioner: bool = False
    is_senior: bool = False


class RegimeResultResponse(BaseModel):
    regime: str
    fy: str
    gross_total_income: str
    standard_deduction: str
    section_24b_deduction: str
    chapter_via_deduction: str
    taxable_income: str
    tax_on_slabs: str
    tax_on_special_rate_income: str
    base_tax: str
    rebate_87a: str
    tax_after_rebate: str
    surcharge: str
    cess: str
    total_tax: str
    notes: list[str] = Field(default_factory=list)


class RegimeComparisonResponse(BaseModel):
    fy: str
    old: RegimeResultResponse
    new: RegimeResultResponse
    recommendation: str  # "old" | "new" | "neutral"
    delta: str  # positive ⇒ new saves
    sources: list[str] = Field(default_factory=list)


class DeductionUtilizationItem(BaseModel):
    section: str
    cap: str | None = None
    claimed: str
    remaining: str | None = None
    description: str


class DeductionUtilizationResponse(BaseModel):
    fy: str
    items: list[DeductionUtilizationItem] = Field(default_factory=list)


class ItrRecommendationInputs(BaseModel):
    total_income: str
    has_business_income: bool = False
    opted_into_presumptive_44ad_44ada: bool = False
    has_capital_gains_non_112a_carveout: bool = False
    has_more_than_one_house_property: bool = False
    has_brought_forward_house_property_loss: bool = False
    has_foreign_asset_or_income: bool = False
    is_director_or_holds_unlisted_shares: bool = False
    agricultural_income: str = "0"
    is_resident: bool = True


class ItrRecommendationResponse(BaseModel):
    form: str
    reasons: list[str] = Field(default_factory=list)
    blockers_for_itr1: list[str] = Field(default_factory=list)


class WhatIfScenarioRequest(BaseModel):
    fy: str
    baseline: RegimeInputs
    scenario_80c: str = "0"
    scenario_80ccd_1b: str = "0"
    scenario_80d_self: str = "0"
    scenario_80d_parents: str = "0"
    scenario_80e: str = "0"
    scenario_80g: str = "0"
    scenario_80tta_or_ttb: str = "0"
    scenario_home_loan_interest_self: str = "0"


class WhatIfResponse(BaseModel):
    fy: str
    baseline: RegimeComparisonResponse
    scenario: RegimeComparisonResponse
    saving_old: str
    saving_new: str


class ReconciliationLineResponse(BaseModel):
    kind: str  # matched | missing_in_ledger | missing_in_portal | amount_mismatch
    label: str
    portal_amount: str | None = None
    ledger_amount: str | None = None
    delta: str | None = None
    portal_date: date | None = None
    ledger_canonical_id: str | None = None
    notes: str


class ReconciliationReportResponse(BaseModel):
    fy: str
    source: str
    matched: int
    missing_in_ledger: int
    missing_in_portal: int
    amount_mismatch: int
    total_portal_amount: str
    total_ledger_amount: str
    lines: list[ReconciliationLineResponse] = Field(default_factory=list)


class ReconciliationBundleResponse(BaseModel):
    fy: str
    reports: list[ReconciliationReportResponse] = Field(default_factory=list)


# -------- Sprint B.4: missing-document checklist -------- #


class ChecklistItemResponse(BaseModel):
    kind: str
    severity: str  # "block_filing" | "warning" | "info"
    title: str
    detail: str
    cta_link: str | None = None
    evidence_count: int = 0


class ChecklistBundleResponse(BaseModel):
    fy: str
    items: list[ChecklistItemResponse] = Field(default_factory=list)

