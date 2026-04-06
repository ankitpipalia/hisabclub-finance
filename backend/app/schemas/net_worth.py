from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class BalanceSnapshotResponse(BaseModel):
    id: str
    account_id: str | None = None
    statement_id: str | None = None
    position_key: str
    label: str
    source_kind: str
    entry_kind: str
    asset_type: str
    institution_name: str | None = None
    account_masked: str | None = None
    currency: str
    balance: float
    as_of_date: date
    is_active: bool
    metadata_json: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class NetWorthHistoryPoint(BaseModel):
    as_of_date: date
    assets: float
    liabilities: float
    net_worth: float


class NetWorthTotals(BaseModel):
    assets: float
    liabilities: float
    net_worth: float
    positions_count: int
    manual_positions_count: int
    latest_snapshot_date: str | None = None


class NetWorthOverviewResponse(BaseModel):
    totals: NetWorthTotals
    history: list[NetWorthHistoryPoint] = Field(default_factory=list)
    positions: list[BalanceSnapshotResponse] = Field(default_factory=list)
    manual_snapshots: list[BalanceSnapshotResponse] = Field(default_factory=list)


class ManualBalanceSnapshotCreateRequest(BaseModel):
    label: str
    entry_kind: str
    asset_type: str
    balance: float
    as_of_date: date
    institution_name: str | None = None
    account_masked: str | None = None
    currency: str = "INR"
    metadata_json: dict | None = None
    position_key: str | None = None
