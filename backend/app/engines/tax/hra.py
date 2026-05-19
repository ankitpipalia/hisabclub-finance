"""HRA (House Rent Allowance) exemption calculator — Sec 10(13A).

HRA exemption is the *minimum* of:
 1. actual HRA received,
 2. 50% of basic+DA if metro (Delhi, Mumbai, Kolkata, Chennai) else 40%,
 3. rent paid minus 10% of basic+DA.

The exemption applies only under the OLD regime. New regime taxes HRA in full
(Sec 115BAC). The optimizer / regime calculator should treat HRA exemption
as a pre-input that reduces gross_salary before being passed to the regime
calculator under old regime; under new regime it is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal("0")
_TWO_DP = Decimal("0.01")
_METRO_CITIES = frozenset({"delhi", "mumbai", "kolkata", "chennai"})


@dataclass(frozen=True)
class HraInputs:
    """All annual figures in ₹."""

    actual_hra_received: Decimal
    rent_paid_annual: Decimal
    basic_plus_da_annual: Decimal
    city: str  # any case; we compare lowercased


@dataclass(frozen=True)
class HraResult:
    """Components of the HRA exemption calculation."""

    component_actual_hra: Decimal
    component_metro_pct: Decimal  # 50% or 40% of basic+DA
    component_rent_minus_10pct_basic: Decimal
    exemption: Decimal  # min of the three (floored at 0)
    is_metro: bool
    notes: tuple[str, ...]


def _r(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


def compute_hra_exemption(inputs: HraInputs) -> HraResult:
    is_metro = (inputs.city or "").strip().lower() in _METRO_CITIES
    pct = Decimal("0.50") if is_metro else Decimal("0.40")
    component_actual = max(_ZERO, inputs.actual_hra_received)
    component_pct = max(_ZERO, inputs.basic_plus_da_annual * pct)
    component_rent = max(
        _ZERO, inputs.rent_paid_annual - (inputs.basic_plus_da_annual * Decimal("0.10"))
    )
    exemption = min(component_actual, component_pct, component_rent)
    notes = (
        f"City classification: {'metro' if is_metro else 'non-metro'}",
        f"Applied factor: {pct * 100}% of basic+DA",
    )
    return HraResult(
        component_actual_hra=_r(component_actual),
        component_metro_pct=_r(component_pct),
        component_rent_minus_10pct_basic=_r(component_rent),
        exemption=_r(exemption),
        is_metro=is_metro,
        notes=notes,
    )
