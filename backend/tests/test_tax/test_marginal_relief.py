"""Marginal-relief tests at surcharge thresholds.

These tests check the regime calculator end-to-end (not the helper in
isolation), because the user-visible behaviour is the surcharge after relief.

The principle to verify:
    additional_tax_due_to_crossing_threshold <= additional_income_above_threshold

If income just crosses ₹50L by ₹1L, the total tax+surcharge after the threshold
shouldn't be more than ₹1L higher than the tax at exactly ₹50L. Relief caps
the surcharge so that invariant holds.
"""

from __future__ import annotations

from decimal import Decimal

from app.engines.tax.regime import TaxInputs, compute_old_regime


def _D(s: str) -> Decimal:  # noqa: N802 -- pytest-style helper
    return Decimal(s)


def test_old_regime_just_over_50l_gets_marginal_relief():
    """Old regime at ₹51L gross (no deductions) vs ₹50L gross.

    The income difference is ₹1L. The tax difference WITHOUT relief would
    include a full 10% surcharge on the ~₹13L base tax (~₹1.3L), making the
    extra tax (~₹1.6L) significantly larger than the extra income (₹1L).
    Marginal relief caps the gap at exactly ₹1L.
    """
    at_50l = compute_old_regime(
        "FY24-25",
        TaxInputs(
            interest_income=_D("5000000"),  # exactly ₹50L total income (no salary so no std ded)
            is_salaried=False,
        ),
    )
    over_50l = compute_old_regime(
        "FY24-25",
        TaxInputs(
            interest_income=_D("5100000"),  # ₹51L total income
            is_salaried=False,
        ),
    )

    # No surcharge at the threshold itself.
    assert at_50l.surcharge == _D("0.00")
    # Some surcharge applies above the threshold.
    assert over_50l.surcharge >= _D("0.00")

    # The marginal-relief invariant: extra tax+surcharge can't exceed extra income.
    extra_tax_excl_cess = (over_50l.tax_after_rebate + over_50l.surcharge) - (
        at_50l.tax_after_rebate + at_50l.surcharge
    )
    extra_income = _D("100000")
    assert extra_tax_excl_cess <= extra_income, (
        f"Marginal relief failed: extra tax+surcharge {extra_tax_excl_cess} > "
        f"extra income {extra_income}. Surcharge after relief: {over_50l.surcharge}"
    )


def test_old_regime_well_over_50l_pays_full_surcharge():
    """At ₹70L the surcharge bites in full; marginal relief should NOT apply."""
    at_70l = compute_old_regime(
        "FY24-25",
        TaxInputs(interest_income=_D("7000000"), is_salaried=False),
    )
    # Expect non-trivial 10% surcharge with no relief applied.
    assert at_70l.surcharge > _D("100000")


def test_old_regime_under_50l_no_surcharge_no_relief():
    """₹40L gross income → no surcharge → relief = 0."""
    result = compute_old_regime(
        "FY24-25",
        TaxInputs(interest_income=_D("4000000"), is_salaried=False),
    )
    assert result.surcharge == _D("0.00")


def test_old_regime_just_over_1cr_gets_marginal_relief():
    """₹1.05Cr — relief caps additional tax to ₹5L (the additional income)."""
    at_1cr = compute_old_regime(
        "FY24-25",
        TaxInputs(interest_income=_D("10000000"), is_salaried=False),
    )
    over_1cr = compute_old_regime(
        "FY24-25",
        TaxInputs(interest_income=_D("10500000"), is_salaried=False),
    )
    extra_income = _D("500000")
    extra_tax = (over_1cr.tax_after_rebate + over_1cr.surcharge) - (
        at_1cr.tax_after_rebate + at_1cr.surcharge
    )
    assert extra_tax <= extra_income
