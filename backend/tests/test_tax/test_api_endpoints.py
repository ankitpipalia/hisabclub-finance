"""API endpoint tests for the Phase 2 tax engine routes.

The endpoints are pure-function over inputs (no DB access), so we call the
handlers directly with mocked auth.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.v1 import tax as tax_api
from app.schemas.tax import (
    ItrRecommendationInputs,
    RegimeInputs,
    WhatIfScenarioRequest,
)

_FAKE_USER = SimpleNamespace(id=uuid.uuid4(), email="t@example.com")


@pytest.mark.asyncio
async def test_post_regime_compare_returns_both_regimes():
    body = RegimeInputs(
        gross_salary="1500000",
        deduction_80c="150000",
        deduction_80d_self="25000",
        home_loan_interest_self="200000",
        is_salaried=True,
    )
    response = await tax_api.post_regime_compare(body, fy="FY24-25", user=_FAKE_USER)

    assert response.fy == "FY24-25"
    assert response.old.regime == "old"
    assert response.new.regime == "new"
    assert response.recommendation in {"old", "new", "neutral"}
    assert response.sources  # FY 24-25 cites at least one source


@pytest.mark.asyncio
async def test_post_regime_compare_rejects_unsupported_fy():
    body = RegimeInputs(gross_salary="1500000")
    with pytest.raises(tax_api.HTTPException) as exc:
        await tax_api.post_regime_compare(body, fy="FY99-00", user=_FAKE_USER)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_deduction_utilization_returns_remaining():
    response = await tax_api.get_deduction_utilization(
        fy="FY24-25",
        user=_FAKE_USER,
        deduction_80c="100000",
    )
    by_section = {item.section: item for item in response.items}
    assert by_section["80C/80CCC/80CCD(1)"].cap == "150000"
    assert by_section["80C/80CCC/80CCD(1)"].claimed == "100000"
    assert by_section["80C/80CCC/80CCD(1)"].remaining == "50000"


@pytest.mark.asyncio
async def test_post_itr_recommend_returns_itr1_for_simple_case():
    body = ItrRecommendationInputs(total_income="1500000")
    response = await tax_api.post_itr_recommend(body, user=_FAKE_USER)
    assert response.form == "ITR-1"


@pytest.mark.asyncio
async def test_post_itr_recommend_returns_itr2_for_high_income():
    body = ItrRecommendationInputs(total_income="6000000")
    response = await tax_api.post_itr_recommend(body, user=_FAKE_USER)
    assert response.form == "ITR-2"
    assert response.blockers_for_itr1


@pytest.mark.asyncio
async def test_post_what_if_returns_old_regime_saving_for_80c_top_up():
    body = WhatIfScenarioRequest(
        fy="FY24-25",
        baseline=RegimeInputs(gross_salary="1500000", is_salaried=True),
        scenario_80c="100000",
    )
    response = await tax_api.post_what_if(body, user=_FAKE_USER)
    # Old regime should save ~₹31,200 (the worked example from
    # test_what_if_top_up_80c_under_old_regime_at_15l).
    assert response.saving_old == "31200.00"
    assert response.saving_new == "0.00"


@pytest.mark.asyncio
async def test_get_supported_fys_lists_three():
    fys = await tax_api.get_supported_fys(user=_FAKE_USER)
    assert "FY24-25" in fys
    assert len(fys) == 3
