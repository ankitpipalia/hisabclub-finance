"""Tax planning summary — FY parsing + rule matching against statutory limits."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.engines.insights.tax_planning import (
    _RULES,
    parse_financial_year,
)


def test_parse_financial_year_handles_fy_prefix_short_form():
    start, end = parse_financial_year("FY24-25")
    assert start == date(2024, 4, 1)
    assert end == date(2025, 3, 31)


def test_parse_financial_year_handles_full_four_digit_year():
    start, end = parse_financial_year("2024-2025")
    assert start == date(2024, 4, 1)
    assert end == date(2025, 3, 31)


def test_parse_financial_year_handles_lowercase_no_prefix():
    start, end = parse_financial_year("25-26")
    assert start == date(2025, 4, 1)
    assert end == date(2026, 3, 31)


def test_parse_financial_year_rejects_garbage():
    with pytest.raises(ValueError):
        parse_financial_year("not-a-year")


def test_rules_cover_expected_sections():
    sections = {section for section, *_ in _RULES}
    assert "80C" in sections
    assert "80D" in sections
    assert "80E" in sections
    assert "80G" in sections
    assert "24b" in sections
    assert "80TTA" in sections


def test_80c_pattern_matches_ppf_and_elss_but_not_random_text():
    pattern = next(rule[2] for rule in _RULES if rule[0] == "80C")
    assert pattern.search("PPF Credit ICICI")
    assert pattern.search("Mutual Fund Tax Saver ELSS")
    assert pattern.search("EPF contribution")
    assert not pattern.search("Swiggy Order")


def test_80d_pattern_matches_health_insurance():
    pattern = next(rule[2] for rule in _RULES if rule[0] == "80D")
    assert pattern.search("HDFC ERGO health insurance premium")
    assert pattern.search("MediClaim Renewal")
    assert not pattern.search("Term insurance premium")


def test_80tta_counts_credits_only():
    counts = {section: counts_credits for section, _l, _p, _lim, counts_credits in _RULES}
    assert counts["80TTA"] is True
    assert counts["80C"] is False


def test_24b_limit_is_two_lakh():
    rule = next(r for r in _RULES if r[0] == "24b")
    assert rule[3] == Decimal("200000")


def test_80c_limit_is_one_fifty():
    rule = next(r for r in _RULES if r[0] == "80C")
    assert rule[3] == Decimal("150000")
