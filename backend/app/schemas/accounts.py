from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class InstitutionResponse(BaseModel):
    id: str
    name: str
    short_name: str
    logo_key: str | None = None
    institution_type: str
    supported_formats: dict = Field(default_factory=dict)
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class AccountResponse(BaseModel):
    id: str
    institution_id: str | None = None
    institution_name: str
    account_type: str
    account_number_masked: str | None = None
    nickname: str | None = None
    status: str
    metadata_json: dict | None = None
    last_statement_date: date | None = None
    opening_date: date | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountCreateRequest(BaseModel):
    institution_name: str
    account_type: str
    account_number_masked: str | None = None
    nickname: str | None = None
    metadata_json: dict | None = None


class AccountUpdateRequest(BaseModel):
    nickname: str | None = None
    status: str | None = None
    metadata_json: dict | None = None


class AccountCoverageRange(BaseModel):
    start: date | None = None
    end: date | None = None


class AccountTreeItem(AccountResponse):
    statement_count: int = 0
    total_transactions: int = 0
    latest_balance: float | None = None
    period_coverage: list[AccountCoverageRange] = Field(default_factory=list)


class InstitutionAccountGroup(BaseModel):
    institution: InstitutionResponse | None = None
    institution_name: str
    accounts: list[AccountTreeItem] = Field(default_factory=list)


class AccountStatementsSummary(BaseModel):
    account: AccountResponse
    statements: list[dict] = Field(default_factory=list)

