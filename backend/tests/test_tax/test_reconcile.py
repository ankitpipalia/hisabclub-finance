"""Tests for tax-portal ↔ ledger reconciliation engines."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.engines.tax.reconcile.ais import reconcile_ais_buckets
from app.engines.tax.reconcile.form16 import reconcile_form16
from app.engines.tax.reconcile.form_26as import (
    reconcile_26as_self_paid_challans,
    reconcile_26as_tds,
)


def _D(s: str) -> Decimal:  # noqa: N802 -- pytest-style helper
    return Decimal(s)


# ----- Form-16 -----


def test_form16_matched_within_tolerance():
    report = reconcile_form16(
        fy="FY24-25",
        form16_gross_salary=_D("1200000"),
        ledger_salary_credits=[
            (date(2024, 4, 30), _D("100000"), str(uuid.uuid4())),
        ] * 12,
    )
    assert report.matched == 1
    assert report.amount_mismatch == 0
    assert report.lines[0].kind == "matched"


def test_form16_amount_mismatch_when_bonus_credited_elsewhere():
    report = reconcile_form16(
        fy="FY24-25",
        form16_gross_salary=_D("1500000"),
        ledger_salary_credits=[
            (date(2024, 4, 30), _D("100000"), str(uuid.uuid4())),
        ] * 12,
    )
    assert report.amount_mismatch == 1
    assert report.matched == 0
    assert "MORE than ledger" in report.lines[0].label


def test_form16_missing_in_portal_when_no_upload():
    report = reconcile_form16(
        fy="FY24-25",
        form16_gross_salary=None,
        ledger_salary_credits=[
            (date(2024, 4, 30), _D("100000"), str(uuid.uuid4())),
        ],
    )
    assert report.missing_in_portal == 1
    assert "no Form-16 uploaded" in report.lines[0].label


def test_form16_missing_in_ledger_when_no_credits():
    report = reconcile_form16(
        fy="FY24-25",
        form16_gross_salary=_D("1200000"),
        ledger_salary_credits=[],
    )
    assert report.missing_in_ledger == 1
    assert "no income credits" in report.lines[0].label


def test_form16_empty_returns_empty_report():
    report = reconcile_form16(
        fy="FY24-25",
        form16_gross_salary=None,
        ledger_salary_credits=[],
    )
    assert report.matched == 0
    assert report.missing_in_ledger == 0
    assert report.missing_in_portal == 0
    assert report.lines == ()


# ----- 26AS TDS -----


def test_26as_tds_matched_within_tolerance():
    report = reconcile_26as_tds(
        fy="FY24-25",
        portal_tds_total=_D("100000"),
        form16_tds_total=_D("100000"),
    )
    assert report.matched == 1


def test_26as_tds_with_interest_cert_contribution():
    """Form-16 TDS + interest-cert TDS should sum to 26AS total."""
    report = reconcile_26as_tds(
        fy="FY24-25",
        portal_tds_total=_D("105000"),
        form16_tds_total=_D("100000"),
        interest_cert_tds_total=_D("5000"),
    )
    assert report.matched == 1


def test_26as_tds_amount_mismatch():
    report = reconcile_26as_tds(
        fy="FY24-25",
        portal_tds_total=_D("110000"),
        form16_tds_total=_D("100000"),
    )
    assert report.amount_mismatch == 1
    assert "MORE TDS" in report.lines[0].label


def test_26as_tds_missing_portal():
    report = reconcile_26as_tds(
        fy="FY24-25",
        portal_tds_total=None,
        form16_tds_total=_D("100000"),
    )
    assert report.missing_in_portal == 1


def test_26as_tds_missing_documents():
    report = reconcile_26as_tds(
        fy="FY24-25",
        portal_tds_total=_D("100000"),
        form16_tds_total=None,
    )
    assert report.missing_in_ledger == 1


# ----- 26AS self-paid challans -----


def test_26as_self_paid_matched():
    report = reconcile_26as_self_paid_challans(
        fy="FY24-25",
        portal_self_paid_total=_D("50000"),
        ledger_tax_debits=[(date(2024, 12, 15), _D("50000"), str(uuid.uuid4()))],
    )
    assert report.matched == 1


def test_26as_self_paid_missing_in_portal():
    report = reconcile_26as_self_paid_challans(
        fy="FY24-25",
        portal_self_paid_total=_D("0"),
        ledger_tax_debits=[(date(2024, 12, 15), _D("50000"), str(uuid.uuid4()))],
    )
    assert report.missing_in_portal == 1


def test_26as_self_paid_missing_in_ledger():
    report = reconcile_26as_self_paid_challans(
        fy="FY24-25",
        portal_self_paid_total=_D("50000"),
        ledger_tax_debits=[],
    )
    assert report.missing_in_ledger == 1


# ----- AIS buckets -----


def test_ais_buckets_all_matched():
    report = reconcile_ais_buckets(
        fy="FY24-25",
        ais_salary=_D("1200000"),
        ais_interest=_D("25000"),
        ais_dividend=_D("5000"),
        ais_securities_sold=None,
        ledger_salary=_D("1200000"),
        ledger_interest=_D("25000"),
        ledger_dividend=_D("5000"),
    )
    assert report.matched == 3


def test_ais_securities_sold_flags_capital_gains_workflow():
    report = reconcile_ais_buckets(
        fy="FY24-25",
        ais_salary=_D("1200000"),
        ais_interest=None,
        ais_dividend=None,
        ais_securities_sold=_D("500000"),
        ledger_salary=_D("1200000"),
        ledger_interest=Decimal("0"),
        ledger_dividend=Decimal("0"),
    )
    # 1 matched (salary) + 1 missing_in_ledger for the CG flag
    assert report.matched == 1
    assert any(
        line.kind == "missing_in_ledger" and "Securities sold" in line.label
        for line in report.lines
    )


def test_ais_dividend_only_in_ledger():
    report = reconcile_ais_buckets(
        fy="FY24-25",
        ais_salary=None,
        ais_interest=None,
        ais_dividend=None,
        ais_securities_sold=None,
        ledger_salary=Decimal("0"),
        ledger_interest=Decimal("0"),
        ledger_dividend=_D("8000"),
    )
    assert report.missing_in_portal >= 1
