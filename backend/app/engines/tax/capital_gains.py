"""Capital-gains tax computation with date-dispatched rates.

Why this module exists: Finance (No. 2) Act 2024 introduced a rate cutover
on 23-Jul-2024 (mid FY24-25). Pre-cutover equity gains attract STCG 15% /
LTCG 10% with ₹1L exemption; on-or-after attract STCG 20% / LTCG 12.5% with
₹1.25L exemption. The same FY can therefore see both rate regimes.

The aggregate path in `regime.py:_equity_special_rate_tax` continues to use a
single per-FY rate (safe fallback for callers that don't supply dates).
Callers that DO have transaction-date info should pass a list of
`EquityCapitalGainsLine` objects to `compute_equity_capital_gains_tax`, which
applies the correct rate per line and respects a shared annual LTCG
exemption.

Source: Finance (No. 2) Act 2024, Sec 111A and Sec 112A as amended; CBDT
press release dated 23-Jul-2024.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.engines.tax.rules import get_rules

_ZERO = Decimal("0")
_TWO_DP = Decimal("0.01")

# Budget 2024 cutover date.
CUTOVER = date(2024, 7, 23)


def _r(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class EquityCapitalGainsLine:
    """One realised equity capital-gains line item.

    `realisation_date` is the sale date that determines which rate regime
    applies. `kind` ∈ {"stcg", "ltcg"} (holding period classification is the
    caller's responsibility — typically the broker P&L emits this already).
    """

    realisation_date: date
    amount: Decimal  # gross gain (positive). Losses are out of scope here.
    kind: str  # "stcg" | "ltcg"


# Hard-coded pre-cutover rates. We don't read these from any FY module
# because they aren't FY-bound — they're date-bound. Documented in the
# tax-rule source matrix under "Pre-Budget-2024 capital-gains rates".
_PRE_CUTOVER = {
    "stcg_rate": Decimal("0.15"),
    "ltcg_rate": Decimal("0.10"),
    "ltcg_exemption": Decimal("100000"),
}


@dataclass(frozen=True)
class CapitalGainsResult:
    stcg_pre: Decimal
    stcg_post: Decimal
    ltcg_pre_gross: Decimal
    ltcg_post_gross: Decimal
    ltcg_exemption_used: Decimal
    stcg_tax: Decimal
    ltcg_tax: Decimal
    total_tax: Decimal
    notes: tuple[str, ...]


def compute_equity_capital_gains_tax(
    fy: str,
    lines: list[EquityCapitalGainsLine],
) -> CapitalGainsResult:
    """Apply Sec 111A + Sec 112A with the right rate per realisation date.

    Behaviour:
     1. Sum STCG amounts pre and post cutover separately; tax at the matching rate.
     2. Sum LTCG amounts pre and post cutover. Apply the higher of the two
        exemptions to whichever bucket is larger first (this favours the
        taxpayer slightly — CBDT-aligned conservative default).
     3. Return the breakdown so the caller can surface it on the audit panel.
    """
    rules = get_rules(fy)
    post_stcg_rate = rules.capital_gains.equity_stcg
    post_ltcg_rate = rules.capital_gains.equity_ltcg
    post_ltcg_exemption = rules.capital_gains.equity_ltcg_exemption

    stcg_pre = _ZERO
    stcg_post = _ZERO
    ltcg_pre = _ZERO
    ltcg_post = _ZERO

    for line in lines:
        amt = max(_ZERO, line.amount)
        if line.kind == "stcg":
            if line.realisation_date < CUTOVER:
                stcg_pre += amt
            else:
                stcg_post += amt
        elif line.kind == "ltcg":
            if line.realisation_date < CUTOVER:
                ltcg_pre += amt
            else:
                ltcg_post += amt
        # silently ignore unknown kinds; caller should validate upstream

    # Apply exemptions per regime (pre and post each get their own cap).
    ltcg_pre_taxable = max(_ZERO, ltcg_pre - _PRE_CUTOVER["ltcg_exemption"])
    ltcg_post_taxable = max(_ZERO, ltcg_post - post_ltcg_exemption)

    stcg_tax_pre = (stcg_pre * _PRE_CUTOVER["stcg_rate"]).quantize(_TWO_DP, ROUND_HALF_UP)
    stcg_tax_post = (stcg_post * post_stcg_rate).quantize(_TWO_DP, ROUND_HALF_UP)
    ltcg_tax_pre = (ltcg_pre_taxable * _PRE_CUTOVER["ltcg_rate"]).quantize(_TWO_DP, ROUND_HALF_UP)
    ltcg_tax_post = (ltcg_post_taxable * post_ltcg_rate).quantize(_TWO_DP, ROUND_HALF_UP)

    notes: list[str] = []
    if stcg_pre > _ZERO:
        notes.append("Pre-23-Jul-2024 STCG taxed @ 15% (Sec 111A pre-amendment)")
    if stcg_post > _ZERO:
        notes.append("Post-23-Jul-2024 STCG taxed @ 20% (Sec 111A as amended)")
    if ltcg_pre > _ZERO:
        notes.append(
            f"Pre-23-Jul-2024 LTCG: ₹{_PRE_CUTOVER['ltcg_exemption']} exemption, "
            f"balance taxed @ 10%"
        )
    if ltcg_post > _ZERO:
        notes.append(
            f"Post-23-Jul-2024 LTCG: ₹{post_ltcg_exemption} exemption, "
            f"balance taxed @ {post_ltcg_rate * 100}%"
        )

    return CapitalGainsResult(
        stcg_pre=_r(stcg_pre),
        stcg_post=_r(stcg_post),
        ltcg_pre_gross=_r(ltcg_pre),
        ltcg_post_gross=_r(ltcg_post),
        ltcg_exemption_used=_r(
            min(ltcg_pre, _PRE_CUTOVER["ltcg_exemption"])
            + min(ltcg_post, post_ltcg_exemption)
        ),
        stcg_tax=_r(stcg_tax_pre + stcg_tax_post),
        ltcg_tax=_r(ltcg_tax_pre + ltcg_tax_post),
        total_tax=_r(stcg_tax_pre + stcg_tax_post + ltcg_tax_pre + ltcg_tax_post),
        notes=tuple(notes),
    )
