"""Classifier maps recurring patterns to user-meaningful buckets."""

from __future__ import annotations

import pytest

from app.engines.insights.recurring_classifier import classify_recurring


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Monthly Rent — Mr. Sharma", "rent"),
        ("BESCOM Electricity Bill", "utility"),
        ("Tata Power", "utility"),
        ("Jio Fiber Broadband", "utility"),
        ("Recharge — Postpaid", "utility"),
        ("HDFC Home Loan EMI", "emi"),
        ("Car Loan Installment 24/60", "emi"),
        ("Education Loan", "emi"),
        ("LIC Premium", "insurance"),
        ("ICICI Pru Term Plan", "insurance"),
        ("Netflix", "subscription"),
        ("Spotify Premium", "subscription"),
        ("CULT.FIT Annual", "subscription"),
        ("Salary Credit — SIMFORM", "salary"),
        ("Payroll April 2026", "salary"),
        ("SIP — Mirae Asset", "investment"),
        ("PPF Contribution", "investment"),
        ("Random Merchant XYZ", "other"),
        ("", "other"),
    ],
)
def test_classify_recurring_label(description: str, expected: str):
    assert classify_recurring(description) == expected


def test_category_name_used_as_fallback():
    assert classify_recurring("Auto-debit ICICI", "Rent") == "rent"
    assert classify_recurring("auto-debit", "Utilities") == "utility"


def test_category_does_not_override_description_match():
    # Description has a strong signal — that wins over category overlap.
    assert classify_recurring("Netflix Streaming", "Bills") == "subscription"
