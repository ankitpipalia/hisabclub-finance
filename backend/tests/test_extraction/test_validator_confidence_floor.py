"""Verify the validator honors the runtime promotion_confidence_threshold.

Audit C4 (LLM trust): the confidence floor for routing a transaction into
review must follow `settings.promotion_confidence_threshold` rather than the
hardcoded 0.75. This test pins the behavior so future refactors don't silently
revert to the literal.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.extraction.models import ExtractionSource, RawTransaction
from app.extraction.validator import validate_transaction


def _raw(confidence: float) -> RawTransaction:
    return RawTransaction(
        source=ExtractionSource.LLM_TEXT,
        date_raw="2024-04-12",
        description_raw="Amazon Fresh",
        amount_raw="₹250.00",
        txn_type_raw="DR",
        balance_raw="₹4500.00",
        confidence=confidence,
        source_evidence={},
        page_number=1,
        char_offset=0,
    )


def test_confidence_above_threshold_marks_valid():
    settings.promotion_confidence_threshold = 0.6
    txn = validate_transaction(_raw(confidence=0.85))
    assert txn.validation_status.value == "valid"


def test_confidence_below_threshold_marks_low_confidence():
    settings.promotion_confidence_threshold = 0.8
    txn = validate_transaction(_raw(confidence=0.7))
    assert txn.validation_status.value == "low_confidence"


def test_zero_confidence_marks_low_even_with_default_threshold():
    settings.promotion_confidence_threshold = 0.75
    txn = validate_transaction(_raw(confidence=0.0))
    assert txn.validation_status.value == "low_confidence"


@pytest.fixture(autouse=True)
def _restore_threshold():
    original = settings.promotion_confidence_threshold
    yield
    settings.promotion_confidence_threshold = original
