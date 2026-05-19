"""ITR form recommender for resident individuals (non-business).

Decision tree (per Income Tax Department's ITR-selection guide, AY 2025-26):

 - **ITR-1 (Sahaj)**: resident individual; total income ≤ ₹50L; income from
   salary/pension + one house property (not let-out with brought-forward loss)
   + other sources (interest, dividend) + LTCG u/s 112A up to ₹1.25L (FY24-25+).
   NOT eligible if: director in a company, holds unlisted shares, foreign
   asset, agricultural income > ₹5,000, capital gains other than the LTCG
   carve-out, business/profession income.

 - **ITR-2**: individual/HUF with no business/profession income but ineligible
   for ITR-1 (e.g. capital gains, multiple house properties, total income
   > ₹50L, foreign assets, etc.).

 - **ITR-3**: individual/HUF having income from business/profession.

 - **ITR-4 (Sugam)**: resident individual/HUF/firm (not LLP) with presumptive
   business/professional income u/s 44AD / 44ADA / 44AE; total income ≤ ₹50L.

This module is intentionally narrow to non-business personal scope. If the
user has *any* business/profession income, we return ITR-3 (or ITR-4 when
the user explicitly opts into presumptive taxation), and add a note that
HisabClub does not yet model business filings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


_FIFTY_LAKH = Decimal("5000000")


@dataclass(frozen=True)
class ItrInputs:
    """Caller-supplied profile flags."""

    total_income: Decimal
    has_business_income: bool = False
    opted_into_presumptive_44ad_44ada: bool = False
    has_capital_gains_non_112a_carveout: bool = False
    has_more_than_one_house_property: bool = False
    has_brought_forward_house_property_loss: bool = False
    has_foreign_asset_or_income: bool = False
    is_director_or_holds_unlisted_shares: bool = False
    agricultural_income: Decimal = Decimal("0")
    is_resident: bool = True


@dataclass(frozen=True)
class ItrRecommendation:
    form: str  # "ITR-1" | "ITR-2" | "ITR-3" | "ITR-4"
    reasons: tuple[str, ...]
    blockers_for_itr1: tuple[str, ...] = field(default_factory=tuple)


def recommend_itr_form(inputs: ItrInputs) -> ItrRecommendation:
    blockers: list[str] = []

    if not inputs.is_resident:
        blockers.append("Non-resident: ITR-1 only applies to residents.")
    if inputs.total_income > _FIFTY_LAKH:
        blockers.append("Total income exceeds ₹50,00,000 (ITR-1 cap).")
    if inputs.has_capital_gains_non_112a_carveout:
        blockers.append("Has capital gains beyond the ITR-1 LTCG carve-out.")
    if inputs.has_more_than_one_house_property:
        blockers.append("Owns more than one house property.")
    if inputs.has_brought_forward_house_property_loss:
        blockers.append("Has brought-forward house property loss.")
    if inputs.has_foreign_asset_or_income:
        blockers.append("Has foreign assets or income.")
    if inputs.is_director_or_holds_unlisted_shares:
        blockers.append("Is a company director or holds unlisted equity shares.")
    if inputs.agricultural_income > Decimal("5000"):
        blockers.append("Agricultural income exceeds ₹5,000.")

    # Business / profession income routes to ITR-3 or ITR-4.
    if inputs.has_business_income:
        if (
            inputs.opted_into_presumptive_44ad_44ada
            and inputs.total_income <= _FIFTY_LAKH
            and not inputs.has_capital_gains_non_112a_carveout
            and not inputs.has_foreign_asset_or_income
            and inputs.is_resident
        ):
            return ItrRecommendation(
                form="ITR-4",
                reasons=(
                    "Has business / profession income reported on a presumptive "
                    "basis (Sec 44AD / 44ADA / 44AE) and meets ITR-4 eligibility.",
                    "HisabClub focuses on non-business personal scope — review "
                    "ITR-4 details with a CA before filing.",
                ),
            )
        return ItrRecommendation(
            form="ITR-3",
            reasons=(
                "Has business / profession income, which is outside ITR-1/ITR-2.",
                "HisabClub focuses on non-business personal scope; ITR-3 is "
                "recommended for filing.",
            ),
        )

    if not blockers:
        return ItrRecommendation(
            form="ITR-1",
            reasons=(
                "Resident individual with total income ≤ ₹50L from salary, one "
                "house property, and other sources — ITR-1 (Sahaj) is the "
                "lightest applicable form.",
            ),
        )

    return ItrRecommendation(
        form="ITR-2",
        reasons=(
            "Ineligible for ITR-1 due to disqualifiers; no business / "
            "profession income, so ITR-2 applies.",
        ),
        blockers_for_itr1=tuple(blockers),
    )
