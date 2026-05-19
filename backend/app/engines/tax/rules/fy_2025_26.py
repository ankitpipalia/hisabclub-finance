"""FY 2025-26 (AY 2026-27) Indian personal income tax rules.

Sources (retrieved 2026-05-20):
 - Union Budget 2025 — new regime slabs revised; rebate 87A under new
   regime raised to ₹60,000 with income threshold ₹12L. Std deduction
   for salaried remains ₹75,000. Old regime largely unchanged.
 - https://www.indiabudget.gov.in/
 - https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm
 - CBDT FAQ on new regime (Feb 2025)

Scope: resident individual, non-business.
"""

from decimal import Decimal

from app.engines.tax.rules.types import (
    CapitalGainsRates,
    Rebate87A,
    RegimeRules,
    SectionLimits,
    SlabBracket,
    SurchargeBracket,
    TaxRules,
)

_INF = Decimal("Infinity")

# ----- New regime slabs (post-Budget 2025) -----
# Budget 2025: 0–4L: nil, 4–8L: 5%, 8–12L: 10%, 12–16L: 15%, 16–20L: 20%,
# 20–24L: 25%, above 24L: 30%. (Marginal-relief rules from CBDT remain.)
_NEW_REGIME_SLABS = (
    SlabBracket(upto=Decimal("400000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("800000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("1200000"), rate=Decimal("0.10")),
    SlabBracket(upto=Decimal("1600000"), rate=Decimal("0.15")),
    SlabBracket(upto=Decimal("2000000"), rate=Decimal("0.20")),
    SlabBracket(upto=Decimal("2400000"), rate=Decimal("0.25")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# Old regime: unchanged.
_OLD_REGIME_SLABS = (
    SlabBracket(upto=Decimal("250000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# Senior (60-79) and super-senior (≥80) old-regime slabs (unchanged from earlier FYs).
_OLD_REGIME_SLABS_SENIOR = (
    SlabBracket(upto=Decimal("300000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)
_OLD_REGIME_SLABS_SUPER_SENIOR = (
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

_OLD_SURCHARGE = (
    SurchargeBracket(threshold=Decimal("5000000"), rate=Decimal("0.10")),
    SurchargeBracket(threshold=Decimal("10000000"), rate=Decimal("0.15")),
    SurchargeBracket(threshold=Decimal("20000000"), rate=Decimal("0.25")),
    SurchargeBracket(threshold=Decimal("50000000"), rate=Decimal("0.37")),
)
_NEW_SURCHARGE = (
    SurchargeBracket(threshold=Decimal("5000000"), rate=Decimal("0.10")),
    SurchargeBracket(threshold=Decimal("10000000"), rate=Decimal("0.15")),
    SurchargeBracket(threshold=Decimal("20000000"), rate=Decimal("0.25")),
)

_OLD_REBATE_87A = Rebate87A(
    income_threshold=Decimal("500000"),
    max_rebate=Decimal("12500"),
)
# New regime 87A (Budget 2025): rebate up to ₹60,000 for income ≤ ₹12L.
_NEW_REBATE_87A = Rebate87A(
    income_threshold=Decimal("1200000"),
    max_rebate=Decimal("60000"),
)

_CESS_RATE = Decimal("0.04")

_SECTION_LIMITS = SectionLimits(
    sec_80c=Decimal("150000"),
    sec_80ccd_1b=Decimal("50000"),
    sec_80d_self_under_60=Decimal("25000"),
    sec_80d_self_senior=Decimal("50000"),
    sec_80d_parents_under_60=Decimal("25000"),
    sec_80d_parents_senior=Decimal("50000"),
    sec_80d_preventive_inside_cap=Decimal("5000"),
    sec_80tta=Decimal("10000"),
    sec_80ttb=Decimal("50000"),
    sec_80gg_monthly_cap=Decimal("5000"),
    sec_24b_self_occupied=Decimal("200000"),
    sec_24b_letout=None,
    sec_80e_cap=None,
)

# Capital gains rates carried forward from FY24-25 changes.
_CAPITAL_GAINS = CapitalGainsRates(
    equity_stcg=Decimal("0.20"),
    equity_ltcg=Decimal("0.125"),
    equity_ltcg_exemption=Decimal("125000"),
    debt_stcg_rate=None,
    debt_ltcg_rate=None,
    other_ltcg_rate=Decimal("0.125"),
    other_ltcg_with_indexation=False,
)

RULES = TaxRules(
    fy="FY25-26",
    fy_start_year=2025,
    old_regime=RegimeRules(
        slabs=_OLD_REGIME_SLABS,
        standard_deduction_salary=Decimal("50000"),
        standard_deduction_pension=Decimal("50000"),
        rebate_87a=_OLD_REBATE_87A,
        surcharge_brackets=_OLD_SURCHARGE,
        cess_rate=_CESS_RATE,
        slabs_senior=_OLD_REGIME_SLABS_SENIOR,
        slabs_super_senior=_OLD_REGIME_SLABS_SUPER_SENIOR,
    ),
    new_regime=RegimeRules(
        slabs=_NEW_REGIME_SLABS,
        standard_deduction_salary=Decimal("75000"),
        standard_deduction_pension=Decimal("75000"),
        rebate_87a=_NEW_REBATE_87A,
        surcharge_brackets=_NEW_SURCHARGE,
        cess_rate=_CESS_RATE,
    ),
    section_limits=_SECTION_LIMITS,
    capital_gains=_CAPITAL_GAINS,
    sources=(
        "Union Budget 2025-26",
        "https://www.indiabudget.gov.in/",
        "https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm",
    ),
)
