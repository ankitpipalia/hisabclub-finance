"""FY 2023-24 (AY 2024-25) Indian personal income tax rules.

Sources (retrieved 2026-05-20):
 - https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm
 - Finance Act 2023 — new regime restructured (Sec 115BAC(1A)),
   std deduction ₹50,000 extended to new regime.
 - https://incometaxindia.gov.in/news/cir-no-1-2024.pdf

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

# ----- New regime slabs (Sec 115BAC(1A), Finance Act 2023) -----
_NEW_REGIME_SLABS = (
    SlabBracket(upto=Decimal("300000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("600000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("900000"), rate=Decimal("0.10")),
    SlabBracket(upto=Decimal("1200000"), rate=Decimal("0.15")),
    SlabBracket(upto=Decimal("1500000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# ----- Old regime slabs -----
_OLD_REGIME_SLABS = (
    SlabBracket(upto=Decimal("250000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.05")),
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
_NEW_REBATE_87A = Rebate87A(
    income_threshold=Decimal("700000"),
    max_rebate=Decimal("25000"),
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

# Pre-Budget-2024 capital gains: equity LTCG 10% > ₹1L, STCG 15%.
_CAPITAL_GAINS = CapitalGainsRates(
    equity_stcg=Decimal("0.15"),
    equity_ltcg=Decimal("0.10"),
    equity_ltcg_exemption=Decimal("100000"),
    debt_stcg_rate=None,
    debt_ltcg_rate=None,
    other_ltcg_rate=Decimal("0.20"),  # 20% with indexation pre Jul-2024
    other_ltcg_with_indexation=True,
)

RULES = TaxRules(
    fy="FY23-24",
    fy_start_year=2023,
    old_regime=RegimeRules(
        slabs=_OLD_REGIME_SLABS,
        standard_deduction_salary=Decimal("50000"),
        standard_deduction_pension=Decimal("50000"),
        rebate_87a=_OLD_REBATE_87A,
        surcharge_brackets=_OLD_SURCHARGE,
        cess_rate=_CESS_RATE,
    ),
    new_regime=RegimeRules(
        slabs=_NEW_REGIME_SLABS,
        standard_deduction_salary=Decimal("50000"),
        standard_deduction_pension=Decimal("50000"),
        rebate_87a=_NEW_REBATE_87A,
        surcharge_brackets=_NEW_SURCHARGE,
        cess_rate=_CESS_RATE,
    ),
    section_limits=_SECTION_LIMITS,
    capital_gains=_CAPITAL_GAINS,
    sources=(
        "Finance Act 2023",
        "https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm",
    ),
)
