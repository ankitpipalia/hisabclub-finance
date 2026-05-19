"""Tests for HRA calculator and deductions utilization/what-if."""

from __future__ import annotations

from decimal import Decimal

from app.engines.tax.deductions import (
    WhatIfScenario,
    compute_utilization,
    what_if,
)
from app.engines.tax.hra import HraInputs, compute_hra_exemption
from app.engines.tax.regime import TaxInputs


def _D(s: str) -> Decimal:  # noqa: N802 -- pytest-style helper
    return Decimal(s)


# ----- HRA -----


def test_hra_metro_min_is_rent_minus_10pct_basic():
    """₹50k/m rent, ₹40k/m HRA, ₹80k/m basic in Mumbai.
    Annual: rent ₹6L, HRA ₹4.8L, basic ₹9.6L.
    Three components:
     - actual HRA = ₹4.8L
     - 50% of basic (metro) = ₹4.8L
     - rent - 10% basic = ₹6L - ₹96k = ₹5.04L
    Min = ₹4.8L."""
    result = compute_hra_exemption(
        HraInputs(
            actual_hra_received=_D("480000"),
            rent_paid_annual=_D("600000"),
            basic_plus_da_annual=_D("960000"),
            city="Mumbai",
        )
    )
    assert result.is_metro is True
    assert result.component_actual_hra == _D("480000.00")
    assert result.component_metro_pct == _D("480000.00")
    assert result.component_rent_minus_10pct_basic == _D("504000.00")
    assert result.exemption == _D("480000.00")


def test_hra_non_metro_uses_40pct():
    """Non-metro city should apply 40% factor."""
    result = compute_hra_exemption(
        HraInputs(
            actual_hra_received=_D("100000"),
            rent_paid_annual=_D("120000"),
            basic_plus_da_annual=_D("400000"),
            city="Pune",
        )
    )
    assert result.is_metro is False
    assert result.component_metro_pct == _D("160000.00")  # 40% of 4L
    # rent - 10% basic = 120k - 40k = 80k → min is 80k
    assert result.component_rent_minus_10pct_basic == _D("80000.00")
    assert result.exemption == _D("80000.00")


def test_hra_zero_rent_is_zero_exemption():
    result = compute_hra_exemption(
        HraInputs(
            actual_hra_received=_D("100000"),
            rent_paid_annual=_D("0"),
            basic_plus_da_annual=_D("400000"),
            city="Mumbai",
        )
    )
    assert result.exemption == _D("0.00")


# ----- Deductions utilization -----


def test_utilization_reports_cap_and_remaining_per_section():
    report = compute_utilization(
        "FY24-25",
        claims={"deduction_80c": _D("100000"), "deduction_80d_self": _D("15000")},
    )
    by_section = {item.section: item for item in report.items}

    assert by_section["80C/80CCC/80CCD(1)"].cap == _D("150000")
    assert by_section["80C/80CCC/80CCD(1)"].claimed == _D("100000")
    assert by_section["80C/80CCC/80CCD(1)"].remaining == _D("50000")

    assert by_section["80D (self)"].cap == _D("25000")
    assert by_section["80D (self)"].claimed == _D("15000")
    assert by_section["80D (self)"].remaining == _D("10000")


def test_utilization_no_cap_section_has_none_remaining():
    report = compute_utilization(
        "FY24-25", claims={"deduction_80e": _D("75000")}
    )
    item = next(i for i in report.items if i.section == "80E")
    assert item.cap is None
    assert item.remaining is None


def test_utilization_senior_uses_higher_80d_and_80ttb():
    report = compute_utilization(
        "FY24-25",
        claims={"deduction_80d_self": _D("0")},
        is_senior=True,
    )
    by_section = {item.section: item for item in report.items}
    assert by_section["80D (self)"].cap == _D("50000")
    assert by_section["80TTA/80TTB"].cap == _D("50000")


# ----- What-if -----


def test_what_if_top_up_80c_under_old_regime_at_15l():
    """Bump 80C from ₹0 → ₹1L at ₹15L salary under old regime.
    Old regime taxable falls from ₹14.5L (after ₹50k std) to ₹13.5L.
    Slab tax at ₹14.5L: 0 + ₹12.5k (5% on 2.5L) + ₹100k (20% on 5L) + ₹135k (30% on 4.5L) = ₹247.5k
    Slab tax at ₹13.5L: 0 + ₹12.5k + ₹100k + ₹105k (30% on 3.5L) = ₹217.5k
    Saving on slabs = ₹30k. Plus 4% cess saving on ₹30k = ₹1.2k. Total saving = ₹31,200."""
    baseline = TaxInputs(gross_salary=_D("1500000"), is_salaried=True)
    scenario = WhatIfScenario(deduction_80c=_D("100000"))
    result = what_if("FY24-25", baseline, scenario)
    assert result.saving_old == _D("31200.00")
    # New regime ignores 80C → no saving under new.
    assert result.saving_new == _D("0.00")


def test_what_if_80ccd_1b_works_independently_of_80c():
    """₹50k NPS via 80CCD(1B) lifts the deductible amount even when 80C is full."""
    baseline = TaxInputs(
        gross_salary=_D("1500000"),
        deduction_80c=_D("150000"),
        is_salaried=True,
    )
    scenario = WhatIfScenario(deduction_80ccd_1b=_D("50000"))
    result = what_if("FY24-25", baseline, scenario)
    assert result.saving_old > _D("0")
