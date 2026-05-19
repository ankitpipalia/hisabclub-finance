"""Worked-example tests for the regime calculator.

Each test fixes a specific FY + caller profile and asserts the total tax
matches a hand-calculation (or the official CBDT calculator). If a test
breaks because Indian tax rules changed, do NOT amend the test — instead
ship a new FY module + a new test for that FY.
"""

from __future__ import annotations

from decimal import Decimal

from app.engines.tax.regime import (
    TaxInputs,
    compare,
    compute_new_regime,
    compute_old_regime,
)


def _D(s: str) -> Decimal:
    return Decimal(s)


# ----- FY 24-25 worked examples -----


def test_fy_24_25_new_regime_taxable_7l_pays_zero_thanks_to_87a():
    """₹7.75L gross salary - ₹75k std deduction = ₹7L taxable.
    Tax = 0 on first 3L + 5% on ₹4L = ₹20k.
    87A rebate caps at ₹25k for taxable ≤ ₹7L → tax = 0.
    Cess on 0 = 0. Total = 0."""
    inputs = TaxInputs(gross_salary=_D("775000"), is_salaried=True)
    result = compute_new_regime("FY24-25", inputs)
    assert result.taxable_income == _D("700000.00")
    assert result.tax_on_slabs == _D("20000.00")
    assert result.rebate_87a == _D("20000.00")  # rebate ≤ min(base_tax, cap)
    assert result.total_tax == _D("0.00")


def test_fy_24_25_new_regime_at_15l_salary_no_deductions():
    """₹15.75L salary - ₹75k std = ₹15L taxable.
    New regime FY24-25 slabs: 0-3L 0%, 3-7L 5% (=₹20k), 7-10L 10% (=₹30k),
    10-12L 15% (=₹30k), 12-15L 20% (=₹60k). Total slab tax = ₹140,000.
    Income > ₹7L → no 87A. Cess 4% on ₹140k = ₹5,600. Total = ₹145,600."""
    inputs = TaxInputs(gross_salary=_D("1575000"), is_salaried=True)
    result = compute_new_regime("FY24-25", inputs)
    assert result.taxable_income == _D("1500000.00")
    assert result.tax_on_slabs == _D("140000.00")
    assert result.rebate_87a == _D("0.00")
    assert result.cess == _D("5600.00")
    assert result.total_tax == _D("145600.00")


def test_fy_24_25_old_regime_with_80c_and_80d():
    """Salaried, ₹15L gross, ₹1.5L 80C, ₹25k 80D self, ₹50k std.
    GTI = 15L; deductions = std 50k + 80C 1.5L + 80D 25k = 2.25L.
    Taxable = 12.75L.
    Old slabs: 0-2.5L 0%, 2.5-5L 5% (₹12,500), 5-10L 20% (₹100,000),
    >10L 30% on ₹2.75L (₹82,500). Total slab = ₹195,000.
    Not eligible for 87A (taxable > ₹5L).
    No surcharge (GTI ₹15L < ₹50L). Cess 4% = ₹7,800. Total = ₹202,800."""
    inputs = TaxInputs(
        gross_salary=_D("1500000"),
        deduction_80c=_D("150000"),
        deduction_80d_self=_D("25000"),
        is_salaried=True,
    )
    result = compute_old_regime("FY24-25", inputs)
    assert result.taxable_income == _D("1275000.00")
    assert result.tax_on_slabs == _D("195000.00")
    assert result.cess == _D("7800.00")
    assert result.total_tax == _D("202800.00")


def test_fy_24_25_old_regime_80c_cap_enforced():
    """User contributes ₹2L to 80C — only ₹1.5L is deductible."""
    inputs = TaxInputs(
        gross_salary=_D("1000000"),
        deduction_80c=_D("200000"),  # > cap
        is_salaried=True,
    )
    result = compute_old_regime("FY24-25", inputs)
    assert result.chapter_via_deduction == _D("150000.00")  # capped


def test_fy_24_25_new_regime_ignores_80c_and_80d():
    """New regime drops 80C / 80D — caller submits them but they are ignored."""
    inputs = TaxInputs(
        gross_salary=_D("1000000"),
        deduction_80c=_D("150000"),
        deduction_80d_self=_D("25000"),
        is_salaried=True,
    )
    result = compute_new_regime("FY24-25", inputs)
    assert result.chapter_via_deduction == _D("0.00")


def test_fy_24_25_employer_nps_80ccd_2_honoured_under_new_regime():
    """80CCD(2) is one of the few Chapter VI-A deductions allowed under new."""
    inputs = TaxInputs(
        gross_salary=_D("1500000"),
        deduction_80ccd_2=_D("100000"),
        is_salaried=True,
    )
    result = compute_new_regime("FY24-25", inputs)
    assert result.chapter_via_deduction == _D("100000.00")


def test_fy_24_25_home_loan_self_occupied_caps_at_2l_under_old():
    """Old regime: home-loan interest on self-occupied is capped at ₹2L."""
    inputs = TaxInputs(
        gross_salary=_D("2000000"),
        home_loan_interest_self=_D("350000"),  # > cap
        is_salaried=True,
    )
    result = compute_old_regime("FY24-25", inputs)
    assert result.section_24b_deduction == _D("200000.00")


def test_fy_24_25_home_loan_self_occupied_disallowed_under_new():
    """New regime: self-occupied home-loan interest is NOT deductible."""
    inputs = TaxInputs(
        gross_salary=_D("2000000"),
        home_loan_interest_self=_D("200000"),
        is_salaried=True,
    )
    result = compute_new_regime("FY24-25", inputs)
    assert result.section_24b_deduction == _D("0.00")


def test_fy_24_25_equity_ltcg_125k_exemption_applied():
    """Equity LTCG of ₹2L on top of ₹10L salary.
    Exemption ₹1.25L under FY24-25 → ₹75k taxable @ 12.5% = ₹9,375.
    Slab tax on ₹9.25L salary (after ₹75k std) — pure new regime numbers:
    ₹9.25L taxable: 0-3L 0%, 3-7L 5% (₹20k), 7-9.25L 10% (₹22.5k) = ₹42,500.
    Total base tax = ₹42,500 + ₹9,375 = ₹51,875.
    No 87A (taxable > ₹7L). Cess 4% on ₹51,875 = ₹2,075.
    Total = ₹53,950."""
    inputs = TaxInputs(
        gross_salary=_D("1000000"),
        capital_gain_equity_ltcg=_D("200000"),
        is_salaried=True,
    )
    result = compute_new_regime("FY24-25", inputs)
    assert result.tax_on_slabs == _D("42500.00")
    assert result.tax_on_special_rate_income == _D("9375.00")
    assert result.cess == _D("2075.00")
    assert result.total_tax == _D("53950.00")


# ----- compare() recommendation -----


def test_compare_recommends_new_when_no_deductions_at_15l():
    """A salaried earner at ₹15L with no deductions should usually pick new regime."""
    inputs = TaxInputs(gross_salary=_D("1500000"), is_salaried=True)
    result = compare("FY24-25", inputs)
    assert result.recommendation == "new"
    assert result.delta > Decimal("0")


def test_compare_recommends_old_with_heavy_deductions():
    """A salaried earner at ₹15L with ₹1.5L 80C + ₹50k 80CCD(1B) + ₹25k 80D +
    ₹2L home-loan should usually win on old."""
    inputs = TaxInputs(
        gross_salary=_D("1500000"),
        deduction_80c=_D("150000"),
        deduction_80ccd_1b=_D("50000"),
        deduction_80d_self=_D("25000"),
        home_loan_interest_self=_D("200000"),
        is_salaried=True,
    )
    result = compare("FY24-25", inputs)
    assert result.recommendation == "old"
    assert result.delta < Decimal("0")


# ----- FY 25-26 -----


def test_fy_25_26_new_regime_at_12l_pays_zero_thanks_to_higher_87a():
    """Budget 2025: new regime 87A rebate raised to ₹60k for income ≤ ₹12L.
    ₹12.75L salary - ₹75k std = ₹12L taxable.
    New slabs: 0-4L 0%, 4-8L 5% (₹20k), 8-12L 10% (₹40k) = ₹60k slab tax.
    Rebate ₹60k → tax = 0."""
    inputs = TaxInputs(gross_salary=_D("1275000"), is_salaried=True)
    result = compute_new_regime("FY25-26", inputs)
    assert result.taxable_income == _D("1200000.00")
    assert result.tax_on_slabs == _D("60000.00")
    assert result.rebate_87a == _D("60000.00")
    assert result.total_tax == _D("0.00")
