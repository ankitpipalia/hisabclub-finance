"""Type definitions for FY-versioned tax rules.

These dataclasses are the canonical shape for the FY modules and for the
regime calculator. They are *intentionally* not Pydantic models — they are
pure-data, immutable, hashable, and easy to reason about in tests.

Conventions:
 - Money values are `Decimal` (rupees, not paise) so arithmetic stays exact.
 - Slab thresholds are inclusive of the *upper* bound and exclusive of the
   *lower* bound, matching how the Income Tax Department documents slabs
   (e.g. "₹3L–₹6L → 5%"). The first slab's lower bound is implicit 0.
 - Surcharge brackets follow the same convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class SlabBracket:
    """A single slab band.

    `upto` is the inclusive upper income bound. `Decimal("Infinity")` for the
    top open-ended bracket.
    """

    upto: Decimal
    rate: Decimal  # e.g. Decimal("0.05") for 5%


@dataclass(frozen=True)
class SurchargeBracket:
    """Surcharge bracket.

    Applied on the *base income tax* (after slabs, before cess) when total
    income exceeds `threshold`. Health & Education Cess is computed AFTER
    surcharge.
    """

    threshold: Decimal
    rate: Decimal


@dataclass(frozen=True)
class Rebate87A:
    """Section 87A rebate parameters.

    `income_threshold`: total taxable income must be ≤ this for rebate to
    apply. `max_rebate`: capped rebate amount.
    """

    income_threshold: Decimal
    max_rebate: Decimal


@dataclass(frozen=True)
class CapitalGainsRates:
    """Capital gains rates relevant to personal/non-business taxpayers."""

    # Equity & equity MF — Section 111A / 112A. Holding > 12 months = LTCG.
    equity_stcg: Decimal  # flat rate on STCG of equity (Sec 111A)
    equity_ltcg: Decimal  # flat rate on LTCG of equity beyond exemption (Sec 112A)
    equity_ltcg_exemption: Decimal  # annual exemption (e.g. ₹1L or ₹1.25L)

    # Debt MF / unlisted securities — treated as per slab if STCG, varied for LTCG.
    debt_stcg_rate: Decimal | None  # None means "as per slab"
    debt_ltcg_rate: Decimal | None  # None means "as per slab"

    # Listed bonds / gold / RE etc — Section 112. LTCG flat rate (with or w/o
    # indexation depending on FY rules).
    other_ltcg_rate: Decimal | None
    other_ltcg_with_indexation: bool


@dataclass(frozen=True)
class SectionLimits:
    """Deduction caps by section.

    All amounts are annual ₹ caps unless otherwise documented in the FY module.
    `None` means "not applicable for this FY" — typically because the entire
    deduction tree is unavailable under the regime in question.
    """

    sec_80c: Decimal  # combined 80C/80CCC/80CCD(1) ceiling (Sec 80CCE)
    sec_80ccd_1b: Decimal  # additional NPS, on top of 80CCE
    sec_80d_self_under_60: Decimal
    sec_80d_self_senior: Decimal  # 60+
    sec_80d_parents_under_60: Decimal
    sec_80d_parents_senior: Decimal  # 60+
    sec_80d_preventive_inside_cap: Decimal  # ₹5k cap that fits *inside* the 80D limits
    sec_80tta: Decimal  # savings interest (non-senior)
    sec_80ttb: Decimal  # savings + FD interest (senior 60+)
    sec_80gg_monthly_cap: Decimal  # ₹5k/month; consumed by 80GG `min(...)` calc
    sec_24b_self_occupied: Decimal  # home-loan interest, self-occupied
    sec_24b_letout: Decimal | None  # None = no cap (actual interest deductible)
    sec_80e_cap: Decimal | None  # None = no cap (actual interest, 8 years)


@dataclass(frozen=True)
class RegimeRules:
    """Per-regime slabs + std deduction + 87A."""

    slabs: tuple[SlabBracket, ...]
    standard_deduction_salary: Decimal
    standard_deduction_pension: Decimal
    rebate_87a: Rebate87A
    surcharge_brackets: tuple[SurchargeBracket, ...]
    cess_rate: Decimal  # Health & Education Cess on (tax + surcharge)


@dataclass(frozen=True)
class TaxRules:
    """Complete FY tax rules: both regimes + section limits + capital gains."""

    fy: str  # e.g. "FY24-25"
    fy_start_year: int  # e.g. 2024 (the AY would be 2025-26)
    old_regime: RegimeRules
    new_regime: RegimeRules
    section_limits: SectionLimits
    capital_gains: CapitalGainsRates
    # Free-form notes that the API surfaces in the "rule basis" field of
    # tax recommendations, so every recommendation can be traced to a citation.
    sources: tuple[str, ...] = field(default_factory=tuple)
