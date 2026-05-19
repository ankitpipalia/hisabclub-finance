"""Old vs New regime tax calculator (Indian personal income tax).

Public API:
    compute_old_regime(fy, inputs) -> RegimeResult
    compute_new_regime(fy, inputs) -> RegimeResult
    compare(fy, inputs) -> RegimeComparison

`inputs` is a `TaxInputs` dataclass. Every monetary value is a `Decimal` (in
rupees, not paise). The calculator does not consult the database — it is a
pure function of the FY rules + caller-supplied inputs. This makes it easy
to test against worked examples.

Scope (matches §1 of master_plan_2026.md): resident individual, non-business.
Senior/super-senior special slabs (Sec 80U etc.) are not yet modelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.engines.tax.rules import get_rules
from app.engines.tax.rules.types import RegimeRules, SlabBracket, TaxRules

_TWO_DP = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")


def _round_inr(amount: Decimal) -> Decimal:
    """Round to nearest paisa (the Income Tax Act rounds to nearest rupee for
    payable tax, but we keep two-decimal precision so the UI/API can re-round
    presentationally without compounding error)."""
    return amount.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TaxInputs:
    """Caller-facing tax inputs.

    All monetary values are gross/positive ₹ amounts; the calculator handles
    rounding + cap enforcement. Deductions that don't apply under the new
    regime are silently dropped by `compute_new_regime`.
    """

    # Income (in ₹)
    gross_salary: Decimal = _ZERO  # before std deduction
    interest_income: Decimal = _ZERO
    dividend_income: Decimal = _ZERO
    rental_income_net: Decimal = _ZERO  # already net of 30% std + municipal tax
    business_income: Decimal = _ZERO  # included for completeness; non-business scope only
    other_income: Decimal = _ZERO

    # Capital gains (calculator does not classify; caller computes upstream)
    capital_gain_equity_stcg: Decimal = _ZERO
    capital_gain_equity_ltcg: Decimal = _ZERO  # gross, before per-FY exemption
    capital_gain_other: Decimal = _ZERO  # taxed at slab unless caller plugs special rate

    # Deductions (old regime only, unless explicitly noted)
    deduction_80c: Decimal = _ZERO  # combined 80C/80CCC/80CCD(1)
    deduction_80ccd_1b: Decimal = _ZERO  # additional NPS
    deduction_80ccd_2: Decimal = _ZERO  # employer NPS (applies under BOTH regimes)
    deduction_80d_self: Decimal = _ZERO
    deduction_80d_parents: Decimal = _ZERO
    deduction_80e: Decimal = _ZERO
    deduction_80g: Decimal = _ZERO  # caller already computed after 50%/100% with/without cap
    deduction_80gg: Decimal = _ZERO  # rent paid w/o HRA (caller computes the min formula)
    deduction_80tta_or_ttb: Decimal = _ZERO  # caller picks the right one based on age
    home_loan_interest_self: Decimal = _ZERO  # for self-occupied; capped per FY
    home_loan_interest_letout: Decimal = _ZERO  # uncapped (lossable up to ₹2L/yr against other heads)

    # Flags
    is_salaried: bool = True  # toggles the std deduction lookup
    is_pensioner: bool = False
    is_senior: bool = False  # 60+
    is_super_senior: bool = False  # 80+


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RegimeResult:
    """Per-regime breakdown."""

    regime: str  # "old" | "new"
    fy: str

    # Build-up
    gross_total_income: Decimal
    standard_deduction: Decimal
    section_24b_deduction: Decimal  # home-loan interest applied here (against rental + other heads)
    chapter_via_deduction: Decimal  # 80C + 80CCD(1B) + 80D + 80E + 80G + 80GG + 80TTA/B (+ 80CCD(2) under new)
    taxable_income: Decimal

    # Tax stack
    tax_on_slabs: Decimal
    tax_on_special_rate_income: Decimal  # equity STCG/LTCG (and similar)
    base_tax: Decimal  # tax_on_slabs + tax_on_special_rate_income
    rebate_87a: Decimal
    tax_after_rebate: Decimal
    surcharge: Decimal
    cess: Decimal
    total_tax: Decimal

    # Breakdown / audit
    slab_breakdown: tuple[tuple[Decimal, Decimal, Decimal], ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RegimeComparison:
    fy: str
    old: RegimeResult
    new: RegimeResult
    recommendation: str  # "old" | "new" | "neutral"
    delta: Decimal  # positive ⇒ new saves ₹delta vs old


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _apply_slabs(
    taxable: Decimal,
    slabs: tuple[SlabBracket, ...],
) -> tuple[Decimal, tuple[tuple[Decimal, Decimal, Decimal], ...]]:
    """Compute slab-based tax. Returns (total, ((from, to, tax), ...))."""
    if taxable <= _ZERO:
        return _ZERO, ()
    total = _ZERO
    breakdown: list[tuple[Decimal, Decimal, Decimal]] = []
    lower = _ZERO
    for slab in slabs:
        if taxable <= lower:
            break
        upper_in_slab = min(taxable, slab.upto)
        chunk = upper_in_slab - lower
        if chunk <= _ZERO:
            lower = slab.upto
            continue
        tax_for_chunk = (chunk * slab.rate).quantize(_TWO_DP, rounding=ROUND_HALF_UP)
        total += tax_for_chunk
        breakdown.append((lower, upper_in_slab, tax_for_chunk))
        lower = slab.upto
    return total, tuple(breakdown)


def _apply_surcharge(base_tax: Decimal, total_income: Decimal, regime: RegimeRules) -> Decimal:
    if base_tax <= _ZERO:
        return _ZERO
    applicable_rate = _ZERO
    for bracket in regime.surcharge_brackets:
        if total_income > bracket.threshold:
            applicable_rate = bracket.rate
        else:
            break
    if applicable_rate == _ZERO:
        return _ZERO
    return _round_inr(base_tax * applicable_rate)


def _apply_87a(taxable: Decimal, base_tax: Decimal, regime: RegimeRules) -> Decimal:
    """Section 87A rebate.

    Returns the rebate amount (a non-negative value to be subtracted from
    base_tax). Excess of base_tax over rebate cap is not rebated.
    """
    if taxable > regime.rebate_87a.income_threshold:
        return _ZERO
    if base_tax <= _ZERO:
        return _ZERO
    return min(base_tax, regime.rebate_87a.max_rebate)


def _std_deduction_for(inputs: TaxInputs, regime: RegimeRules) -> Decimal:
    if inputs.is_salaried:
        return regime.standard_deduction_salary
    if inputs.is_pensioner:
        return regime.standard_deduction_pension
    return _ZERO


def _gross_total_income(inputs: TaxInputs) -> Decimal:
    return (
        inputs.gross_salary
        + inputs.interest_income
        + inputs.dividend_income
        + inputs.rental_income_net
        + inputs.business_income
        + inputs.other_income
        + inputs.capital_gain_other
    )


def _equity_special_rate_tax(inputs: TaxInputs, rules: TaxRules) -> tuple[Decimal, tuple[str, ...]]:
    """Tax equity STCG (Sec 111A) + LTCG (Sec 112A) at FY-specific rates.

    Note: these rates are the *same* under both regimes; only slab income
    differs across regimes. Caller passes gross capital gain amounts and the
    calculator applies the per-FY exemption to LTCG.
    """
    cg = rules.capital_gains
    notes: list[str] = []
    stcg_tax = (inputs.capital_gain_equity_stcg * cg.equity_stcg).quantize(
        _TWO_DP, rounding=ROUND_HALF_UP
    )
    ltcg_after_exemption = max(
        _ZERO, inputs.capital_gain_equity_ltcg - cg.equity_ltcg_exemption
    )
    ltcg_tax = (ltcg_after_exemption * cg.equity_ltcg).quantize(
        _TWO_DP, rounding=ROUND_HALF_UP
    )
    if inputs.capital_gain_equity_ltcg > _ZERO:
        notes.append(
            f"Equity LTCG: ₹{cg.equity_ltcg_exemption} exemption applied; "
            f"taxed @ {cg.equity_ltcg * 100}%"
        )
    if inputs.capital_gain_equity_stcg > _ZERO:
        notes.append(f"Equity STCG taxed @ {cg.equity_stcg * 100}% (Sec 111A)")
    return stcg_tax + ltcg_tax, tuple(notes)


# --------------------------------------------------------------------------- #
# Old regime
# --------------------------------------------------------------------------- #


def compute_old_regime(fy: str, inputs: TaxInputs) -> RegimeResult:
    rules = get_rules(fy)
    regime = rules.old_regime
    limits = rules.section_limits

    gti = _gross_total_income(inputs)
    std_ded = _std_deduction_for(inputs, regime)

    # Section 24(b) — home-loan interest. Self-occupied is capped; let-out
    # uncapped (per current rules).
    sec_24b = min(inputs.home_loan_interest_self, limits.sec_24b_self_occupied)
    sec_24b += inputs.home_loan_interest_letout  # uncapped

    # Chapter VI-A deductions (old regime).
    chapter_via = _chapter_via_old(inputs, limits)
    # 80CCD(2) employer NPS applies under old too, though most users hit it
    # via salary slips; we accept it from inputs.
    chapter_via += inputs.deduction_80ccd_2

    taxable = max(_ZERO, gti - std_ded - sec_24b - chapter_via)

    # Slab tax on the *non-special-rate* taxable income.
    # Equity gains are special-rate, so we subtract them from `taxable` for
    # slab purposes only if the caller has included them in gross income.
    # Convention: caller passes equity STCG/LTCG ONLY via capital_gain_equity_*;
    # they are NOT part of other_income/etc. So `taxable` excludes them.
    slab_tax, slab_breakdown = _apply_slabs(taxable, regime.slabs)
    special_tax, special_notes = _equity_special_rate_tax(inputs, rules)
    base_tax = slab_tax + special_tax

    # 87A rebate applies to slab tax only (not to Sec 111A/112A special-rate
    # tax — long-standing CBDT position; conservative approach).
    rebate = _apply_87a(taxable, slab_tax, regime)
    tax_after_rebate = max(_ZERO, base_tax - rebate)

    surcharge = _apply_surcharge(tax_after_rebate, gti, regime)
    cess = _round_inr((tax_after_rebate + surcharge) * regime.cess_rate)
    total = _round_inr(tax_after_rebate + surcharge + cess)

    return RegimeResult(
        regime="old",
        fy=rules.fy,
        gross_total_income=_round_inr(gti),
        standard_deduction=_round_inr(std_ded),
        section_24b_deduction=_round_inr(sec_24b),
        chapter_via_deduction=_round_inr(chapter_via),
        taxable_income=_round_inr(taxable),
        tax_on_slabs=_round_inr(slab_tax),
        tax_on_special_rate_income=_round_inr(special_tax),
        base_tax=_round_inr(base_tax),
        rebate_87a=_round_inr(rebate),
        tax_after_rebate=_round_inr(tax_after_rebate),
        surcharge=_round_inr(surcharge),
        cess=_round_inr(cess),
        total_tax=total,
        slab_breakdown=slab_breakdown,
        notes=special_notes,
    )


def _chapter_via_old(inputs: TaxInputs, limits) -> Decimal:
    # 80C / 80CCC / 80CCD(1) combined ceiling.
    sec_80c = min(inputs.deduction_80c, limits.sec_80c)
    # 80CCD(1B) — additional ₹50k for NPS, on top of 80CCE.
    sec_80ccd_1b = min(inputs.deduction_80ccd_1b, limits.sec_80ccd_1b)
    # 80D (caller passes already-summed self+parents in the two buckets).
    sec_80d_self_cap = (
        limits.sec_80d_self_senior if inputs.is_senior else limits.sec_80d_self_under_60
    )
    sec_80d_parents_cap = limits.sec_80d_parents_senior  # parents likely seniors;
    # caller should split if needed. Conservative: cap at senior limit which is the higher value.
    sec_80d = min(inputs.deduction_80d_self, sec_80d_self_cap) + min(
        inputs.deduction_80d_parents, sec_80d_parents_cap
    )
    sec_80e = inputs.deduction_80e  # no cap
    sec_80g = inputs.deduction_80g  # caller computed
    sec_80gg = inputs.deduction_80gg
    sec_80tta_ttb = min(
        inputs.deduction_80tta_or_ttb,
        limits.sec_80ttb if inputs.is_senior else limits.sec_80tta,
    )
    return (
        sec_80c
        + sec_80ccd_1b
        + sec_80d
        + sec_80e
        + sec_80g
        + sec_80gg
        + sec_80tta_ttb
    )


# --------------------------------------------------------------------------- #
# New regime
# --------------------------------------------------------------------------- #


def compute_new_regime(fy: str, inputs: TaxInputs) -> RegimeResult:
    rules = get_rules(fy)
    regime = rules.new_regime

    gti = _gross_total_income(inputs)
    std_ded = _std_deduction_for(inputs, regime)

    # Under new regime: most Chapter VI-A deductions are NOT available.
    # The ones that *are* allowed (per Sec 115BAC(2)) include 80CCD(2)
    # (employer NPS contribution). We do NOT honor 80C/80D/80E/etc.
    chapter_via_allowed = inputs.deduction_80ccd_2

    # Sec 24(b) home-loan interest on a SELF-occupied house is NOT deductible
    # under the new regime. Let-out property interest IS still allowed (set-off
    # restricted to ₹2L against other heads of income).
    sec_24b = min(inputs.home_loan_interest_letout, Decimal("200000"))

    taxable = max(_ZERO, gti - std_ded - sec_24b - chapter_via_allowed)

    slab_tax, slab_breakdown = _apply_slabs(taxable, regime.slabs)
    special_tax, special_notes = _equity_special_rate_tax(inputs, rules)
    base_tax = slab_tax + special_tax

    rebate = _apply_87a(taxable, slab_tax, regime)
    tax_after_rebate = max(_ZERO, base_tax - rebate)

    surcharge = _apply_surcharge(tax_after_rebate, gti, regime)
    cess = _round_inr((tax_after_rebate + surcharge) * regime.cess_rate)
    total = _round_inr(tax_after_rebate + surcharge + cess)

    notes = list(special_notes)
    notes.append(
        "New regime: 80C/80D/80E/HRA/24(b)(self-occupied) etc. NOT deductible "
        "per Sec 115BAC(2). Only 80CCD(2) (employer NPS) and let-out home "
        "loan interest are honoured."
    )

    return RegimeResult(
        regime="new",
        fy=rules.fy,
        gross_total_income=_round_inr(gti),
        standard_deduction=_round_inr(std_ded),
        section_24b_deduction=_round_inr(sec_24b),
        chapter_via_deduction=_round_inr(chapter_via_allowed),
        taxable_income=_round_inr(taxable),
        tax_on_slabs=_round_inr(slab_tax),
        tax_on_special_rate_income=_round_inr(special_tax),
        base_tax=_round_inr(base_tax),
        rebate_87a=_round_inr(rebate),
        tax_after_rebate=_round_inr(tax_after_rebate),
        surcharge=_round_inr(surcharge),
        cess=_round_inr(cess),
        total_tax=total,
        slab_breakdown=slab_breakdown,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def compare(fy: str, inputs: TaxInputs) -> RegimeComparison:
    old = compute_old_regime(fy, inputs)
    new = compute_new_regime(fy, inputs)
    delta = old.total_tax - new.total_tax
    if delta > _ZERO:
        recommendation = "new"
    elif delta < _ZERO:
        recommendation = "old"
    else:
        recommendation = "neutral"
    return RegimeComparison(
        fy=old.fy,
        old=old,
        new=new,
        recommendation=recommendation,
        delta=_round_inr(delta),
    )
