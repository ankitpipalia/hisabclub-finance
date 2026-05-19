"""FY 2024-25 (AY 2025-26) Indian personal income tax rules.

Sources (retrieved 2026-05-20):
 - https://incometaxindia.gov.in/Pages/tax-laws-rules.aspx
 - https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm
 - Finance (No. 2) Act, 2024 (Budget July 2024) — new regime slabs revised,
   std deduction raised to ₹75,000 for salaried filers from FY 2024-25.
 - https://incometaxindia.gov.in/Acts/Income-tax%20Act,%201961/2024/index.htm
 - CBDT Notification No. 19/2024 dt. 31-Jan-2024 (forms).
 - https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1

Scope: resident individual, non-business. Senior citizen = age ≥ 60 during PY.
Super-senior = age ≥ 80 (not modelled here yet; see plan §10).
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

# ----- New regime slabs (Sec 115BAC) -----
# Per Finance (No. 2) Act 2024, applicable to FY 2024-25 onward.
_NEW_REGIME_SLABS = (
    SlabBracket(upto=Decimal("300000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("700000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.10")),
    SlabBracket(upto=Decimal("1200000"), rate=Decimal("0.15")),
    SlabBracket(upto=Decimal("1500000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# ----- Old regime slabs (general, age < 60) -----
_OLD_REGIME_SLABS = (
    SlabBracket(upto=Decimal("250000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# ----- Old regime slabs, senior citizen (age 60-79) -----
# Source: https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm
# 0-3L exempt; 3-5L 5%; 5-10L 20%; >10L 30%.
_OLD_REGIME_SLABS_SENIOR = (
    SlabBracket(upto=Decimal("300000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.05")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# ----- Old regime slabs, super-senior citizen (age ≥ 80) -----
# Source: https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm
# 0-5L exempt; 5-10L 20%; >10L 30%.
_OLD_REGIME_SLABS_SUPER_SENIOR = (
    SlabBracket(upto=Decimal("500000"), rate=Decimal("0.00")),
    SlabBracket(upto=Decimal("1000000"), rate=Decimal("0.20")),
    SlabBracket(upto=_INF, rate=Decimal("0.30")),
)

# ----- Surcharge brackets (apply to base tax) -----
# Old regime: 10% > ₹50L, 15% > ₹1Cr, 25% > ₹2Cr, 37% > ₹5Cr.
_OLD_SURCHARGE = (
    SurchargeBracket(threshold=Decimal("5000000"), rate=Decimal("0.10")),
    SurchargeBracket(threshold=Decimal("10000000"), rate=Decimal("0.15")),
    SurchargeBracket(threshold=Decimal("20000000"), rate=Decimal("0.25")),
    SurchargeBracket(threshold=Decimal("50000000"), rate=Decimal("0.37")),
)
# New regime: surcharge capped at 25% above ₹2Cr (37% bracket removed under
# the new regime by Finance Act 2023 onwards).
_NEW_SURCHARGE = (
    SurchargeBracket(threshold=Decimal("5000000"), rate=Decimal("0.10")),
    SurchargeBracket(threshold=Decimal("10000000"), rate=Decimal("0.15")),
    SurchargeBracket(threshold=Decimal("20000000"), rate=Decimal("0.25")),
)

# ----- 87A rebate -----
# Old regime: rebate ₹12,500 if taxable income ≤ ₹5L.
_OLD_REBATE_87A = Rebate87A(
    income_threshold=Decimal("500000"),
    max_rebate=Decimal("12500"),
)
# New regime (Sec 115BAC(1A)): rebate ₹25,000 if taxable income ≤ ₹7L.
_NEW_REBATE_87A = Rebate87A(
    income_threshold=Decimal("700000"),
    max_rebate=Decimal("25000"),
)

# ----- Cess (Health & Education) -----
_CESS_RATE = Decimal("0.04")

# ----- Section limits -----
_SECTION_LIMITS = SectionLimits(
    sec_80c=Decimal("150000"),  # Sec 80CCE ceiling
    sec_80ccd_1b=Decimal("50000"),  # additional NPS
    sec_80d_self_under_60=Decimal("25000"),
    sec_80d_self_senior=Decimal("50000"),
    sec_80d_parents_under_60=Decimal("25000"),
    sec_80d_parents_senior=Decimal("50000"),
    sec_80d_preventive_inside_cap=Decimal("5000"),
    sec_80tta=Decimal("10000"),
    sec_80ttb=Decimal("50000"),
    sec_80gg_monthly_cap=Decimal("5000"),
    sec_24b_self_occupied=Decimal("200000"),
    sec_24b_letout=None,  # no cap; actual interest deductible
    sec_80e_cap=None,  # no cap, 8 years
)

# ----- Capital gains -----
# Note: Finance (No. 2) Act 2024 changed equity LTCG rate to 12.5% with
# exemption raised to ₹1.25L (effective 23-Jul-2024). For pre-23-Jul gains
# the old rates apply — this nuance is not yet modelled at the rules level;
# see capital_gains.py for date-dispatched logic.
_CAPITAL_GAINS = CapitalGainsRates(
    equity_stcg=Decimal("0.20"),  # Sec 111A — raised from 15% to 20% by Budget 2024
    equity_ltcg=Decimal("0.125"),  # 12.5% post 23-Jul-2024
    equity_ltcg_exemption=Decimal("125000"),  # ₹1.25L from 23-Jul-2024
    debt_stcg_rate=None,  # per slab (Specified MFs post 1-Apr-2023)
    debt_ltcg_rate=None,  # per slab for post 1-Apr-2023 specified MFs
    other_ltcg_rate=Decimal("0.125"),  # 12.5% w/o indexation post 23-Jul-2024
    other_ltcg_with_indexation=False,
)

RULES = TaxRules(
    fy="FY24-25",
    fy_start_year=2024,
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
        standard_deduction_salary=Decimal("75000"),  # raised by Budget 2024
        standard_deduction_pension=Decimal("75000"),
        rebate_87a=_NEW_REBATE_87A,
        surcharge_brackets=_NEW_SURCHARGE,
        cess_rate=_CESS_RATE,
    ),
    section_limits=_SECTION_LIMITS,
    capital_gains=_CAPITAL_GAINS,
    sources=(
        "Finance (No. 2) Act 2024",
        "https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm",
        "CBDT Circular No. 6/2024",
    ),
)
