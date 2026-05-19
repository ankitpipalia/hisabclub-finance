"""Deductions optimizer + utilization tracker.

Two distinct services:

1. `compute_utilization(fy, claims)` — given current Chapter VI-A claims,
   show how much of each section's cap is used and what room remains. Drives
   the dashboard "80C utilization" widget.

2. `what_if(fy, baseline_inputs, scenario)` — re-run the regime comparator
   under both regimes with `baseline_inputs + scenario` and return the
   marginal saving. Drives the assistant "what if I top up 80C by ₹X" Q&A.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Mapping

from app.engines.tax.regime import RegimeComparison, TaxInputs, compare
from app.engines.tax.rules import get_rules

_ZERO = Decimal("0")


@dataclass(frozen=True)
class SectionUtilization:
    section: str  # e.g. "80C"
    cap: Decimal | None  # None = no cap
    claimed: Decimal
    remaining: Decimal | None  # None when cap is None
    description: str


@dataclass(frozen=True)
class UtilizationReport:
    fy: str
    items: tuple[SectionUtilization, ...]


def compute_utilization(
    fy: str,
    claims: Mapping[str, Decimal],
    is_senior: bool = False,
) -> UtilizationReport:
    """Return per-section utilization for the given FY.

    `claims` keys should match the field names on `TaxInputs` (e.g.
    `"deduction_80c"`, `"deduction_80ccd_1b"`). Unknown keys are ignored.
    """
    limits = get_rules(fy).section_limits

    def _claim(key: str) -> Decimal:
        return Decimal(str(claims.get(key, _ZERO) or _ZERO))

    sec_80d_self_cap = (
        limits.sec_80d_self_senior if is_senior else limits.sec_80d_self_under_60
    )
    items: list[SectionUtilization] = []

    items.append(
        SectionUtilization(
            section="80C/80CCC/80CCD(1)",
            cap=limits.sec_80c,
            claimed=_claim("deduction_80c"),
            remaining=max(_ZERO, limits.sec_80c - _claim("deduction_80c")),
            description=(
                "Combined ceiling under Sec 80CCE for ELSS / PPF / EPF / LIC / "
                "tax-saving FD / NSC / sukanya / principal / tuition."
            ),
        )
    )
    items.append(
        SectionUtilization(
            section="80CCD(1B)",
            cap=limits.sec_80ccd_1b,
            claimed=_claim("deduction_80ccd_1b"),
            remaining=max(_ZERO, limits.sec_80ccd_1b - _claim("deduction_80ccd_1b")),
            description="Additional NPS contribution — on top of the 80CCE ceiling.",
        )
    )
    items.append(
        SectionUtilization(
            section="80D (self)",
            cap=sec_80d_self_cap,
            claimed=_claim("deduction_80d_self"),
            remaining=max(_ZERO, sec_80d_self_cap - _claim("deduction_80d_self")),
            description=(
                "Medical insurance for self & family. ₹5,000 of preventive "
                "health check-up fits inside this cap."
            ),
        )
    )
    items.append(
        SectionUtilization(
            section="80D (parents)",
            cap=limits.sec_80d_parents_senior,  # show the higher cap as headroom
            claimed=_claim("deduction_80d_parents"),
            remaining=max(
                _ZERO,
                limits.sec_80d_parents_senior - _claim("deduction_80d_parents"),
            ),
            description=(
                "Medical insurance for parents. Cap is ₹50,000 when parents "
                "are senior citizens, else ₹25,000."
            ),
        )
    )
    items.append(
        SectionUtilization(
            section="80E",
            cap=None,
            claimed=_claim("deduction_80e"),
            remaining=None,
            description="Education-loan interest — no cap, deductible up to 8 years.",
        )
    )
    items.append(
        SectionUtilization(
            section="80TTA/80TTB",
            cap=limits.sec_80ttb if is_senior else limits.sec_80tta,
            claimed=_claim("deduction_80tta_or_ttb"),
            remaining=max(
                _ZERO,
                (limits.sec_80ttb if is_senior else limits.sec_80tta)
                - _claim("deduction_80tta_or_ttb"),
            ),
            description=(
                "Savings interest under 80TTA (non-senior ₹10k) or "
                "80TTB (senior ₹50k, also covers FD interest)."
            ),
        )
    )
    items.append(
        SectionUtilization(
            section="24(b) self-occupied",
            cap=limits.sec_24b_self_occupied,
            claimed=_claim("home_loan_interest_self"),
            remaining=max(
                _ZERO, limits.sec_24b_self_occupied - _claim("home_loan_interest_self")
            ),
            description="Home-loan interest on self-occupied house, capped at ₹2L (old regime only).",
        )
    )
    return UtilizationReport(fy=fy, items=tuple(items))


# --------------------------------------------------------------------------- #
# What-if scenarios
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WhatIfScenario:
    """A patch to apply on top of `baseline`. Add only the increments you want
    to model — every unset field defaults to 0 (no change).

    Field names mirror `TaxInputs` so callers can express "add ₹50k to 80C"
    as `WhatIfScenario(deduction_80c=Decimal("50000"))`.
    """

    deduction_80c: Decimal = _ZERO
    deduction_80ccd_1b: Decimal = _ZERO
    deduction_80d_self: Decimal = _ZERO
    deduction_80d_parents: Decimal = _ZERO
    deduction_80e: Decimal = _ZERO
    deduction_80g: Decimal = _ZERO
    deduction_80tta_or_ttb: Decimal = _ZERO
    home_loan_interest_self: Decimal = _ZERO


@dataclass(frozen=True)
class WhatIfResult:
    fy: str
    baseline: RegimeComparison
    scenario: RegimeComparison
    # Positive = the scenario reduces total tax under the recommended regime.
    saving_old: Decimal
    saving_new: Decimal


def what_if(fy: str, baseline: TaxInputs, scenario: WhatIfScenario) -> WhatIfResult:
    """Compute the saving for a deduction-bumping scenario."""
    patched = replace(
        baseline,
        deduction_80c=baseline.deduction_80c + scenario.deduction_80c,
        deduction_80ccd_1b=baseline.deduction_80ccd_1b + scenario.deduction_80ccd_1b,
        deduction_80d_self=baseline.deduction_80d_self + scenario.deduction_80d_self,
        deduction_80d_parents=baseline.deduction_80d_parents
        + scenario.deduction_80d_parents,
        deduction_80e=baseline.deduction_80e + scenario.deduction_80e,
        deduction_80g=baseline.deduction_80g + scenario.deduction_80g,
        deduction_80tta_or_ttb=baseline.deduction_80tta_or_ttb
        + scenario.deduction_80tta_or_ttb,
        home_loan_interest_self=baseline.home_loan_interest_self
        + scenario.home_loan_interest_self,
    )
    base_cmp = compare(fy, baseline)
    scen_cmp = compare(fy, patched)
    return WhatIfResult(
        fy=fy,
        baseline=base_cmp,
        scenario=scen_cmp,
        saving_old=base_cmp.old.total_tax - scen_cmp.old.total_tax,
        saving_new=base_cmp.new.total_tax - scen_cmp.new.total_tax,
    )
