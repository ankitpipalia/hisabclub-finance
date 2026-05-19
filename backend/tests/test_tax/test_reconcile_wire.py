"""Wire-up + endpoint tests for the tax reconciliation bundle.

We mock the DB session to return canonical_transactions + tax_portal_data
fixtures and verify the resulting ReconciliationBundleResponse.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.v1 import tax as tax_api
from app.engines.tax.reconcile.wire import _fy_window


class _ScalarsAllResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return self._values


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _QueuedDb:
    def __init__(self, responses):
        self.responses = list(responses)

    async def execute(self, *_args, **_kwargs):
        return self.responses.pop(0)


def _txn(*, amount, date_, nature, merchant, direction="credit"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        transaction_date=date_,
        amount=Decimal(str(amount)),
        direction=direction,
        transaction_nature=nature,
        merchant_raw=merchant,
        account_type="savings",
        account_masked="XXXX1234",
        is_excluded=False,
    )


def _portal_row(payload):
    return SimpleNamespace(extracted_json=payload)


def test_fy_window_parses_canonical_form():
    start, end = _fy_window("FY24-25")
    assert start == date(2024, 4, 1)
    assert end == date(2025, 3, 31)


def test_fy_window_handles_lowercase():
    start, end = _fy_window("fy24-25")
    assert start == date(2024, 4, 1)


def test_fy_window_rejects_bad_format():
    with pytest.raises(ValueError):
        _fy_window("2024-25")


@pytest.mark.asyncio
async def test_get_reconciliation_bundle_assembles_four_reports(monkeypatch):
    """Bundle endpoint returns one report per source (Form-16, 26AS-TDS,
    26AS-self-paid, AIS) when the user has uploaded all three portal docs."""
    user = SimpleNamespace(id=uuid.uuid4())

    # 12 monthly salary credits across the FY (Apr 2024 → Mar 2025).
    months = [
        (2024, 4), (2024, 5), (2024, 6), (2024, 7), (2024, 8), (2024, 9),
        (2024, 10), (2024, 11), (2024, 12), (2025, 1), (2025, 2), (2025, 3),
    ]
    salary_txns = [
        _txn(
            amount="100000",
            date_=date(yr, mo, 28),
            nature="income",
            merchant=f"SIMFORM SALARY {i}",
        )
        for i, (yr, mo) in enumerate(months)
    ]
    interest_txns = [
        _txn(
            amount="2000",
            date_=date(2024, 6, 30),
            nature="interest_income",
            merchant="HDFC INT",
        )
    ]
    tax_debits = [
        _txn(
            amount="50000",
            date_=date(2024, 12, 15),
            nature="tax",
            merchant="INCOME TAX",
            direction="debit",
        )
    ]
    all_txns_a = _ScalarsAllResult(salary_txns + interest_txns + tax_debits)
    all_txns_b = _ScalarsAllResult(tax_debits)
    all_txns_c = _ScalarsAllResult(salary_txns + interest_txns + tax_debits)

    form16_row = _portal_row(
        {"gross_salary": "1200000", "tds_total": "100000", "employer_name": "ACME"}
    )
    form_26as_row = _portal_row(
        {"tds_total": "100000", "self_paid_total": "50000"}
    )
    ais_row = _portal_row(
        {
            "salary": "1200000",
            "interest": "2000",
            "dividend": "0",
            "securities_sold": "0",
        }
    )

    # Order matches the queries inside run_all_reconciliations:
    # 1) form_16 portal lookup
    # 2) ais portal lookup
    # 3) form_26as portal lookup
    # 4) salary credits query
    # 5) tax debits query
    # 6) aggregate query (salary/interest/dividend)
    db = _QueuedDb(
        [
            _ScalarOneOrNoneResult(form16_row),
            _ScalarOneOrNoneResult(ais_row),
            _ScalarOneOrNoneResult(form_26as_row),
            all_txns_a,
            all_txns_b,
            all_txns_c,
        ]
    )

    response = await tax_api.get_reconciliation_bundle(
        financial_year="FY24-25", user=user, db=db
    )

    assert response.fy == "FY24-25"
    source_set = {report.source for report in response.reports}
    assert source_set == {"Form-16", "26AS", "26AS-self-paid", "AIS"}

    form16_report = next(r for r in response.reports if r.source == "Form-16")
    assert form16_report.matched == 1
    assert form16_report.amount_mismatch == 0

    tds_report = next(r for r in response.reports if r.source == "26AS")
    assert tds_report.matched == 1

    self_paid_report = next(r for r in response.reports if r.source == "26AS-self-paid")
    assert self_paid_report.matched == 1


@pytest.mark.asyncio
async def test_get_reconciliation_bundle_rejects_bad_fy():
    db = _QueuedDb([])
    user = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(tax_api.HTTPException) as exc:
        await tax_api.get_reconciliation_bundle(
            financial_year="not-a-fy", user=user, db=db
        )
    assert exc.value.status_code == 400
