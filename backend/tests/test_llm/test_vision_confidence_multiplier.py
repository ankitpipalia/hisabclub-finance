"""Vision confidence is discounted by settings.vision_confidence_multiplier.

Audit C2 (LLM trust): vision OCR has materially higher hallucination rate on
tabular data than text extraction. Apply a configurable multiplier so review
gates fire earlier on vision-sourced rows without changing template/text paths.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.engines.llm.vision_statement import _apply_vision_confidence_discount


@pytest.fixture(autouse=True)
def _restore_multiplier():
    original = settings.vision_confidence_multiplier
    yield
    settings.vision_confidence_multiplier = original


def test_default_multiplier_is_identity():
    # Default is 1.0 so behavior is unchanged unless an operator opts in.
    settings.vision_confidence_multiplier = 1.0
    assert _apply_vision_confidence_discount(0.9) == pytest.approx(0.9)


def test_recommended_multiplier_discounts_vision_confidence():
    settings.vision_confidence_multiplier = 0.85
    assert _apply_vision_confidence_discount(0.9) == pytest.approx(0.765)


def test_multiplier_zero_clamps_to_zero():
    settings.vision_confidence_multiplier = 0.0
    assert _apply_vision_confidence_discount(0.95) == 0.0


def test_negative_or_oversized_multiplier_is_clamped():
    settings.vision_confidence_multiplier = -0.5
    assert _apply_vision_confidence_discount(0.8) == 0.0
    settings.vision_confidence_multiplier = 1.5
    assert _apply_vision_confidence_discount(0.8) == pytest.approx(0.8)
