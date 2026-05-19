"""Lookup table for FY-versioned tax rules.

Usage:
    >>> from app.engines.tax.rules import get_rules
    >>> rules = get_rules("FY24-25")
    >>> rules.new_regime.standard_deduction_salary
    Decimal('75000')

Adding a new FY:
 1. Create `fy_YYYY_YY.py` modelled after the existing ones; cite sources.
 2. Add the import + entry to `_REGISTRY` below.
 3. Add a worked-example unit test in `tests/test_tax/test_rules_fy*.py`.
 4. Do NOT modify existing FY modules — historical calculations must remain
    reproducible.
"""

from __future__ import annotations

from app.engines.tax.rules.fy_2023_24 import RULES as _FY23_24
from app.engines.tax.rules.fy_2024_25 import RULES as _FY24_25
from app.engines.tax.rules.fy_2025_26 import RULES as _FY25_26
from app.engines.tax.rules.types import TaxRules

_REGISTRY: dict[str, TaxRules] = {
    "FY23-24": _FY23_24,
    "FY24-25": _FY24_25,
    "FY25-26": _FY25_26,
}


def get_rules(fy: str) -> TaxRules:
    """Return the rules for a financial year string like 'FY24-25'.

    Accepts the canonical form `FYYY-YY` only. Raises `ValueError` for any
    unsupported FY so callers fail loudly instead of silently using stale
    rules.
    """
    normalized = (fy or "").strip().upper()
    if normalized in _REGISTRY:
        return _REGISTRY[normalized]
    raise ValueError(
        f"Unsupported financial year: {fy!r}. Supported: {sorted(_REGISTRY)}"
    )


def supported_fys() -> list[str]:
    """Return the list of FY codes the registry currently understands."""
    return sorted(_REGISTRY)
