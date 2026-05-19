"""Date-aware capital-gains tax — pre/post 23-Jul-2024 split.

Critical edge case for FY24-25 because the rate cutover lands mid-FY.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engines.tax.capital_gains import (
    EquityCapitalGainsLine,
    compute_equity_capital_gains_tax,
)


def _D(s: str) -> Decimal:  # noqa: N802
    return Decimal(s)


def test_all_pre_cutover_stcg_taxed_at_15pct():
    """STCG of ₹2L realised on 2024-04-01 → 15% = ₹30k."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 4, 1),
            amount=_D("200000"),
            kind="stcg",
        )
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.stcg_pre == _D("200000.00")
    assert result.stcg_post == _D("0.00")
    assert result.stcg_tax == _D("30000.00")


def test_all_post_cutover_stcg_taxed_at_20pct():
    """STCG of ₹2L realised on 2024-09-01 → 20% = ₹40k."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 9, 1),
            amount=_D("200000"),
            kind="stcg",
        )
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.stcg_post == _D("200000.00")
    assert result.stcg_tax == _D("40000.00")


def test_pre_cutover_ltcg_uses_1l_exemption_and_10pct():
    """LTCG ₹3L pre-cutover → exempt ₹1L, tax 10% on ₹2L = ₹20k."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 5, 1),
            amount=_D("300000"),
            kind="ltcg",
        )
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.ltcg_pre_gross == _D("300000.00")
    assert result.ltcg_tax == _D("20000.00")


def test_post_cutover_ltcg_uses_125k_exemption_and_125pct():
    """LTCG ₹3L post-cutover → exempt ₹1.25L, tax 12.5% on ₹1.75L = ₹21,875."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 10, 1),
            amount=_D("300000"),
            kind="ltcg",
        )
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.ltcg_post_gross == _D("300000.00")
    assert result.ltcg_tax == _D("21875.00")


def test_mixed_pre_and_post_cutover_sums_correctly():
    """One pre-cutover STCG, one post-cutover LTCG."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 5, 1),
            amount=_D("100000"),
            kind="stcg",
        ),  # 15% × 100k = 15k
        EquityCapitalGainsLine(
            realisation_date=date(2024, 10, 1),
            amount=_D("200000"),
            kind="ltcg",
        ),  # 12.5% × (200k - 125k) = 9.375k
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.stcg_tax == _D("15000.00")
    assert result.ltcg_tax == _D("9375.00")
    assert result.total_tax == _D("24375.00")


def test_cutover_date_itself_uses_post_rates():
    """2024-07-23 is the cutover; gains realised that day fall under the new rates."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 7, 23),
            amount=_D("100000"),
            kind="stcg",
        )
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.stcg_pre == _D("0.00")
    assert result.stcg_post == _D("100000.00")
    assert result.stcg_tax == _D("20000.00")  # post-cutover 20% rate


def test_separate_exemptions_per_regime_when_both_present():
    """Pre LTCG ₹150k + Post LTCG ₹150k → pre uses ₹1L exemption, post uses ₹1.25L.
    Pre taxable = ₹50k @ 10% = ₹5k. Post taxable = ₹25k @ 12.5% = ₹3,125.
    Total LTCG tax = ₹8,125."""
    lines = [
        EquityCapitalGainsLine(
            realisation_date=date(2024, 5, 1),
            amount=_D("150000"),
            kind="ltcg",
        ),
        EquityCapitalGainsLine(
            realisation_date=date(2024, 10, 1),
            amount=_D("150000"),
            kind="ltcg",
        ),
    ]
    result = compute_equity_capital_gains_tax("FY24-25", lines)
    assert result.ltcg_tax == _D("8125.00")


def test_empty_lines_returns_zero():
    result = compute_equity_capital_gains_tax("FY24-25", [])
    assert result.total_tax == _D("0.00")
    assert result.stcg_tax == _D("0.00")
    assert result.ltcg_tax == _D("0.00")
