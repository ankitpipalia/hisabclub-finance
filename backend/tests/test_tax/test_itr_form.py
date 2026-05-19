"""ITR form recommender tests."""

from __future__ import annotations

from decimal import Decimal

from app.engines.tax.recommender.itr_form import ItrInputs, recommend_itr_form


def _D(s: str) -> Decimal:
    return Decimal(s)


def test_itr1_for_simple_salaried_under_50l():
    rec = recommend_itr_form(ItrInputs(total_income=_D("1500000")))
    assert rec.form == "ITR-1"


def test_itr2_when_income_above_50l():
    rec = recommend_itr_form(ItrInputs(total_income=_D("6000000")))
    assert rec.form == "ITR-2"
    assert any("₹50,00,000" in b for b in rec.blockers_for_itr1)


def test_itr2_when_holding_foreign_asset():
    rec = recommend_itr_form(
        ItrInputs(total_income=_D("1500000"), has_foreign_asset_or_income=True)
    )
    assert rec.form == "ITR-2"


def test_itr2_when_director_or_unlisted_shares():
    rec = recommend_itr_form(
        ItrInputs(
            total_income=_D("1500000"),
            is_director_or_holds_unlisted_shares=True,
        )
    )
    assert rec.form == "ITR-2"


def test_itr2_when_capital_gains_outside_112a_carveout():
    rec = recommend_itr_form(
        ItrInputs(
            total_income=_D("1500000"),
            has_capital_gains_non_112a_carveout=True,
        )
    )
    assert rec.form == "ITR-2"


def test_itr3_for_any_business_income_without_presumptive():
    rec = recommend_itr_form(
        ItrInputs(total_income=_D("1500000"), has_business_income=True)
    )
    assert rec.form == "ITR-3"


def test_itr4_when_presumptive_44ad_44ada_under_50l():
    rec = recommend_itr_form(
        ItrInputs(
            total_income=_D("3000000"),
            has_business_income=True,
            opted_into_presumptive_44ad_44ada=True,
        )
    )
    assert rec.form == "ITR-4"


def test_itr3_when_presumptive_but_income_over_50l():
    rec = recommend_itr_form(
        ItrInputs(
            total_income=_D("6000000"),
            has_business_income=True,
            opted_into_presumptive_44ad_44ada=True,
        )
    )
    assert rec.form == "ITR-3"


def test_itr2_when_multiple_house_properties_disqualifies_itr1():
    rec = recommend_itr_form(
        ItrInputs(
            total_income=_D("1500000"),
            has_more_than_one_house_property=True,
        )
    )
    assert rec.form == "ITR-2"
