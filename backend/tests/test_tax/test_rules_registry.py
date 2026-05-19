"""Verify the FY tax rules registry returns the right shape per FY.

These tests intentionally hard-code expected slab boundaries and section
limits. Updating an existing FY module without also updating its test fails
the build — that is the contract: historical FY rules MUST stay frozen.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engines.tax.rules import get_rules, supported_fys


def test_supported_fys_lists_canonical_codes():
    assert supported_fys() == ["FY23-24", "FY24-25", "FY25-26"]


def test_unsupported_fy_raises():
    with pytest.raises(ValueError):
        get_rules("FY99-00")


def test_fy_24_25_new_regime_slabs():
    """Verify FY24-25 new regime: 0-3L nil, 3-7L 5%, 7-10L 10%, 10-12L 15%,
    12-15L 20%, >15L 30%. Std deduction ₹75k (Budget 2024)."""
    rules = get_rules("FY24-25")
    slabs = rules.new_regime.slabs

    assert slabs[0].upto == Decimal("300000")
    assert slabs[0].rate == Decimal("0.00")
    assert slabs[1].upto == Decimal("700000")
    assert slabs[1].rate == Decimal("0.05")
    assert slabs[2].upto == Decimal("1000000")
    assert slabs[2].rate == Decimal("0.10")
    assert slabs[3].upto == Decimal("1200000")
    assert slabs[3].rate == Decimal("0.15")
    assert slabs[4].upto == Decimal("1500000")
    assert slabs[4].rate == Decimal("0.20")
    assert slabs[5].rate == Decimal("0.30")

    assert rules.new_regime.standard_deduction_salary == Decimal("75000")
    assert rules.new_regime.rebate_87a.income_threshold == Decimal("700000")
    assert rules.new_regime.rebate_87a.max_rebate == Decimal("25000")


def test_fy_24_25_old_regime_slabs():
    rules = get_rules("FY24-25")
    slabs = rules.old_regime.slabs

    assert slabs[0].upto == Decimal("250000")
    assert slabs[0].rate == Decimal("0.00")
    assert slabs[1].upto == Decimal("500000")
    assert slabs[1].rate == Decimal("0.05")
    assert slabs[2].upto == Decimal("1000000")
    assert slabs[2].rate == Decimal("0.20")
    assert slabs[3].rate == Decimal("0.30")

    assert rules.old_regime.standard_deduction_salary == Decimal("50000")
    assert rules.old_regime.rebate_87a.income_threshold == Decimal("500000")
    assert rules.old_regime.rebate_87a.max_rebate == Decimal("12500")


def test_fy_24_25_section_limits():
    rules = get_rules("FY24-25")
    limits = rules.section_limits

    assert limits.sec_80c == Decimal("150000")
    assert limits.sec_80ccd_1b == Decimal("50000")
    assert limits.sec_80d_self_under_60 == Decimal("25000")
    assert limits.sec_80d_self_senior == Decimal("50000")
    assert limits.sec_80d_parents_under_60 == Decimal("25000")
    assert limits.sec_80d_parents_senior == Decimal("50000")
    assert limits.sec_80d_preventive_inside_cap == Decimal("5000")
    assert limits.sec_80tta == Decimal("10000")
    assert limits.sec_80ttb == Decimal("50000")
    assert limits.sec_24b_self_occupied == Decimal("200000")
    assert limits.sec_24b_letout is None  # no cap
    assert limits.sec_80e_cap is None  # no cap


def test_fy_24_25_capital_gains_post_budget_2024():
    rules = get_rules("FY24-25")
    cg = rules.capital_gains

    # Budget 2024 raised equity STCG to 20% and LTCG to 12.5% (post 23-Jul).
    assert cg.equity_stcg == Decimal("0.20")
    assert cg.equity_ltcg == Decimal("0.125")
    assert cg.equity_ltcg_exemption == Decimal("125000")
    assert cg.other_ltcg_with_indexation is False


def test_fy_23_24_keeps_pre_budget_2024_capital_gains_rates():
    rules = get_rules("FY23-24")
    cg = rules.capital_gains

    assert cg.equity_stcg == Decimal("0.15")
    assert cg.equity_ltcg == Decimal("0.10")
    assert cg.equity_ltcg_exemption == Decimal("100000")
    assert cg.other_ltcg_with_indexation is True


def test_fy_23_24_std_deduction_50k_under_new_regime():
    """FY 23-24 new regime had std deduction ₹50,000 (Budget 2024 raised it to
    ₹75k from FY 24-25)."""
    rules = get_rules("FY23-24")
    assert rules.new_regime.standard_deduction_salary == Decimal("50000")


def test_fy_25_26_new_regime_slabs_post_budget_2025():
    rules = get_rules("FY25-26")
    slabs = rules.new_regime.slabs

    # 0-4L nil, 4-8L 5%, 8-12L 10%, 12-16L 15%, 16-20L 20%, 20-24L 25%, >24L 30%.
    assert slabs[0].upto == Decimal("400000")
    assert slabs[0].rate == Decimal("0.00")
    assert slabs[1].upto == Decimal("800000")
    assert slabs[1].rate == Decimal("0.05")
    assert slabs[2].upto == Decimal("1200000")
    assert slabs[2].rate == Decimal("0.10")
    assert slabs[3].upto == Decimal("1600000")
    assert slabs[3].rate == Decimal("0.15")
    assert slabs[4].upto == Decimal("2000000")
    assert slabs[4].rate == Decimal("0.20")
    assert slabs[5].upto == Decimal("2400000")
    assert slabs[5].rate == Decimal("0.25")
    assert slabs[6].rate == Decimal("0.30")


def test_fy_25_26_new_regime_87a_rebate_raised():
    """Budget 2025: new-regime 87A rebate raised to ₹60,000 for income ≤ ₹12L."""
    rules = get_rules("FY25-26")
    assert rules.new_regime.rebate_87a.income_threshold == Decimal("1200000")
    assert rules.new_regime.rebate_87a.max_rebate == Decimal("60000")


def test_sources_attribution_present_for_every_fy():
    """Every FY module must cite at least one source so the API can surface
    rule-basis citations in tax recommendations."""
    for fy in supported_fys():
        rules = get_rules(fy)
        assert rules.sources, f"FY {fy} has no source attribution"
        assert len(rules.sources) >= 1
