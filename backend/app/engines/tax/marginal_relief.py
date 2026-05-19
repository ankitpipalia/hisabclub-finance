"""Marginal relief on surcharge at slab thresholds.

When total income just crosses a surcharge threshold (₹50L, ₹1Cr, ₹2Cr,
₹5Cr), the entire base tax suddenly attracts surcharge. CBDT allows
"marginal relief": the additional tax due to crossing the threshold cannot
exceed the additional income above the threshold.

This is documented in CBDT illustrations on the new regime FAQs
(https://www.incometax.gov.in/iec/foportal/help/individual) and in the
post-Budget rule books.

Worked example:
  Taxpayer earns ₹51,00,000 (₹1L above the ₹50L threshold). Without relief:
    - base tax on ₹51L (old, no deductions) ≈ ₹13,42,500
    - 10% surcharge = ₹1,34,250
    - tax + surcharge = ₹14,76,750
  Compare to a taxpayer earning exactly ₹50,00,000:
    - base tax ≈ ₹13,12,500, no surcharge → ₹13,12,500.
  Additional tax due to crossing = ₹14,76,750 - ₹13,12,500 = ₹1,64,250.
  Additional income = ₹1,00,000.
  Excess = ₹1,64,250 - ₹1,00,000 = ₹64,250 → relief = ₹64,250.
  Final surcharge after relief = ₹1,34,250 - ₹64,250 = ₹70,000.

This module computes the relief amount; the regime calculator subtracts it
from surcharge before cess.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.engines.tax.rules.types import RegimeRules, SurchargeBracket

_ZERO = Decimal("0")
_TWO_DP = Decimal("0.01")


def _r(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


def _threshold_just_crossed(
    total_income: Decimal,
    brackets: tuple[SurchargeBracket, ...],
) -> SurchargeBracket | None:
    """Return the highest-rate bracket whose threshold has been crossed.

    We only consider one threshold at a time — marginal relief applies at the
    bracket the taxpayer just stepped into. For nested brackets the highest
    triggered one wins.
    """
    crossed: SurchargeBracket | None = None
    for bracket in brackets:
        if total_income > bracket.threshold:
            crossed = bracket
    return crossed


def compute_marginal_relief(
    *,
    total_income: Decimal,
    base_tax: Decimal,
    surcharge: Decimal,
    regime: RegimeRules,
    tax_at_threshold: Decimal | None = None,
) -> Decimal:
    """Compute marginal relief on the *surcharge* portion.

    Args:
        total_income: gross/total income used for surcharge eligibility.
        base_tax: tax computed on slabs before surcharge/cess.
        surcharge: surcharge already computed (without relief).
        regime: the regime whose surcharge brackets we honour.
        tax_at_threshold: optional pre-computed tax on the threshold amount
            itself (used by tests/callers who want exact CBDT-style relief);
            if None, callers can pass the threshold tax recomputed via
            `_apply_slabs` upstream. When omitted, this function returns the
            theoretical maximum relief (capped by current surcharge).

    Returns:
        relief amount to subtract from surcharge. Always ≤ surcharge and ≥ 0.
    """
    if surcharge <= _ZERO or base_tax <= _ZERO:
        return _ZERO

    crossed = _threshold_just_crossed(total_income, regime.surcharge_brackets)
    if crossed is None:
        return _ZERO

    income_over_threshold = total_income - crossed.threshold
    if income_over_threshold <= _ZERO:
        return _ZERO

    # If caller supplied tax_at_threshold, we can compute precise relief:
    # excess_tax = (base_tax + surcharge) - (tax_at_threshold)
    # relief = max(0, excess_tax - income_over_threshold)
    if tax_at_threshold is not None:
        excess_tax = (base_tax + surcharge) - tax_at_threshold
        if excess_tax <= income_over_threshold:
            return _ZERO
        relief = excess_tax - income_over_threshold
        return _r(min(relief, surcharge))

    # Without a precise tax-at-threshold figure, fall back to a conservative
    # approximation: the relief never exceeds the surcharge itself and never
    # exceeds the gap (tax_with_surcharge - income_over_threshold).
    excess_over_income = surcharge - income_over_threshold
    if excess_over_income <= _ZERO:
        return _ZERO
    return _r(min(excess_over_income, surcharge))
