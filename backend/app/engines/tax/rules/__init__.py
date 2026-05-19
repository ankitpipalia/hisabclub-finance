"""FY-versioned Indian personal income tax rules.

Each `fy_YYYY_YY.py` module is a pure-data file describing the slabs,
deductions, and limits applicable for a given financial year. New financial
years ship as new modules; existing modules MUST remain frozen so historical
calculations stay reproducible. Always cite the source URL + retrieval date
for every constant.
"""

from app.engines.tax.rules.registry import get_rules, supported_fys

__all__ = ["get_rules", "supported_fys"]
