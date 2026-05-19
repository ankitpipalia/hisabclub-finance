"""Sprint 1.1 — signal-based scorer + match-kind classifier.

Pure-function tests; no DB. These guarantee the scoring contract so a future
sprint that touches `_score_signals` doesn't quietly regress the dashboard's
"why did this match" explanation.
"""

from __future__ import annotations

from decimal import Decimal

from app.engines.tax.reconcile.line_item import (
    MatchSignals,
    _amount_subscore,
    _classify_match_kind,
    _date_subscore,
    _score_signals,
)


def _D(s: str) -> Decimal:  # noqa: N802 — pytest-style helper
    return Decimal(s)


# ----- subscores -----


def test_amount_subscore_full_credit_at_zero_gap():
    assert _amount_subscore(_D("0"), _D("1000")) == _D("1")


def test_amount_subscore_decays_linearly():
    # gap = 0.5% of total → score ≈ 0.9 (1 - 0.005*20)
    score = _amount_subscore(_D("5"), _D("1000"))
    assert score == _D("0.900")


def test_amount_subscore_zero_at_5_percent_or_more():
    assert _amount_subscore(_D("50"), _D("1000")) == _D("0")
    assert _amount_subscore(_D("60"), _D("1000")) == _D("0")


def test_date_subscore_full_credit_at_same_day():
    assert _date_subscore(0) == _D("1")


def test_date_subscore_half_at_3_days():
    assert _date_subscore(3) == _D("0.5")
    assert _date_subscore(-3) == _D("0.5")


def test_date_subscore_quarter_at_4_to_7_days():
    assert _date_subscore(5) == _D("0.25")


def test_date_subscore_zero_beyond_window():
    assert _date_subscore(8) == _D("0")


# ----- composite score -----


def test_tan_exact_beats_amount_only():
    tan_match = MatchSignals(
        amount_gap=_D("100"),
        portal_amount=_D("100000"),
        date_gap_days=None,
        tan_match=True,
    )
    amount_only = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("100000"),
        date_gap_days=None,
        tan_match=False,
    )
    # tan_match (0.2) + amount_subscore (0.998 * 0.4 = 0.399) = 0.599
    # amount_only: 1.0 * 0.4 = 0.4
    assert _score_signals(tan_match) > _score_signals(amount_only)


def test_same_day_beats_two_day_gap_when_amounts_equal():
    same_day = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
    )
    two_day_gap = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=2,
    )
    assert _score_signals(same_day) > _score_signals(two_day_gap)


def test_pan_only_scored_lower_than_tan():
    pan_only = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=None,
        pan_match=True,
    )
    tan_only = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=None,
        tan_match=True,
    )
    assert _score_signals(tan_only) > _score_signals(pan_only)


def test_employer_match_adds_small_bonus():
    base = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
    )
    with_employer = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
        employer_match=True,
    )
    assert _score_signals(with_employer) > _score_signals(base)
    # The bonus is 0.05.
    delta = _score_signals(with_employer) - _score_signals(base)
    assert delta == _D("0.050")


def test_score_capped_at_1():
    everything = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
        tan_match=True,
        pan_match=True,
        employer_match=True,
    )
    assert _score_signals(everything) == _D("1.000")


def test_empty_signals_returns_zero():
    nothing = MatchSignals(
        amount_gap=None,
        portal_amount=None,
        date_gap_days=None,
    )
    assert _score_signals(nothing) == _D("0")


# ----- match_kind classifier -----


def test_tan_match_classifies_as_tan_exact():
    signals = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
        tan_match=True,
    )
    assert _classify_match_kind(signals) == "tan_exact"


def test_pan_match_overrides_amount_date_window():
    signals = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
        pan_match=True,
    )
    assert _classify_match_kind(signals) == "pan_amount"


def test_employer_match_classifies_as_employer_amount():
    signals = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=None,
        employer_match=True,
    )
    assert _classify_match_kind(signals) == "employer_amount"


def test_same_day_amount_classifies_as_amount_date_window():
    signals = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=0,
    )
    assert _classify_match_kind(signals) == "amount_date_window"


def test_amount_only_fallback_when_no_other_signals():
    signals = MatchSignals(
        amount_gap=_D("0"),
        portal_amount=_D("1000"),
        date_gap_days=None,
    )
    assert _classify_match_kind(signals) == "amount_only_fallback"
