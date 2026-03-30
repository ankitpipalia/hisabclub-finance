from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MonthlySummaryResponse(BaseModel):
    id: str
    year_month: str
    total_income: float
    total_expense: float
    net_flow: float
    category_breakdown: dict | None = None
    top_merchants: list | None = None
    transaction_count: int
    computed_at: datetime
    vs_last_month: float | None = None  # % change in expense vs previous month

    model_config = ConfigDict(from_attributes=True)


class TrendDataPoint(BaseModel):
    month: str
    income: float
    expense: float
    net: float
    category_breakdown: dict | None = None


class TrendResponse(BaseModel):
    months: int
    data: list[TrendDataPoint]


class RecurringPatternResponse(BaseModel):
    id: str
    merchant_name: str | None = None
    description_pattern: str
    typical_amount: float
    amount_variance: float
    frequency: str
    expected_day: int
    last_seen_date: date
    next_expected: date
    is_active: bool
    category_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RecomputeResponse(BaseModel):
    months_computed: int
    message: str


class ReconciliationTransaction(BaseModel):
    id: str
    transaction_date: date
    amount: float
    direction: str
    transaction_nature: str
    merchant_raw: str
    bank_name: str | None = None
    account_type: str | None = None
    account_masked: str | None = None
    source_files: list[str] = Field(default_factory=list)


class ReconciliationMatch(BaseModel):
    amount: float
    day_gap: int
    confidence: float
    reasoning: str
    debit: ReconciliationTransaction
    credit: ReconciliationTransaction


class ReconciliationResponse(BaseModel):
    total_transfer_transactions: int
    matched_pairs: int
    unmatched_transactions: int
    matched_amount: float
    match_rate: float
    pairs: list[ReconciliationMatch]
    unmatched: list[ReconciliationTransaction]


class TaxComplianceTotals(BaseModel):
    total_income: float
    salary_income: float
    interest_income: float
    dividend_income: float
    other_income: float
    total_expense: float
    tax_payments: float
    investment_outflow: float
    transfer_internal: float
    estimated_taxable_income: float
    new_regime_tax_before_rebate: float
    new_regime_rebate: float
    new_regime_tax_after_rebate: float
    new_regime_cess: float
    new_regime_total_tax: float
    new_regime_rebate_threshold: float
    tax_due_or_refund: float
    documented_interest_income: float
    documented_interest_tds: float
    documented_tax_payments: float
    documented_fd_principal: float
    documented_fd_interest: float
    documented_ppf_contribution: float
    documented_ppf_interest: float
    documented_ppf_closing_balance: float
    savings_account_count: float


class TaxComplianceCashItem(BaseModel):
    transaction_id: str
    transaction_date: date
    amount: float
    merchant_raw: str
    bank_name: str | None = None
    account_type: str | None = None


class TaxSavingsAccount(BaseModel):
    bank_name: str
    account_masked: str | None = None
    statement_count: int
    interest_income: float


class TaxLinkageCheck(BaseModel):
    check: str
    status: str
    ledger_amount: float
    document_amount: float
    gap: float
    detail: str


class TaxActionItem(BaseModel):
    severity: str
    title: str
    detail: str


class TaxComplianceResponse(BaseModel):
    period_start: date
    period_end: date
    tax_regime: str
    tax_financial_year: str
    totals: TaxComplianceTotals
    document_coverage: dict[str, int]
    unresolved_statement_docs: int
    high_value_cash_expenses: list[TaxComplianceCashItem]
    savings_accounts: list[TaxSavingsAccount]
    linkage_checks: list[TaxLinkageCheck]
    document_amounts: dict[str, float]
    action_items: list[TaxActionItem]
    tax_notes: list[str]
