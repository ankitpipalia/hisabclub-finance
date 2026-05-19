"""Guard that every FY tax-rule constant is cited in the source matrix.

If you change `engines/tax/rules/fy_*.py` and the new value isn't documented
in `docs/tax-rule-source-matrix.md`, this test fails. The matrix is the
audit trail every tax recommendation cites; out-of-sync = silent drift.

The check is intentionally string-grep, not value-parse. We don't require the
matrix to be machine-parseable — we just require every Decimal token to be
findable in the matrix. False positives (a value that happens to appear in
prose) are acceptable; false negatives (an undocumented value) are not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "docs" / "tax-rule-source-matrix.md"
RULES_DIR = REPO_ROOT / "backend" / "app" / "engines" / "tax" / "rules"

# Constants we know are documented by name in the matrix rather than by value
# (e.g. "₹1,50,000" appears as "₹1,50,000" in prose, but `Decimal("150000")`
# appears in code as a digit literal). We normalize by parsing the literal and
# checking that the value, with or without grouping separators, appears in the
# matrix.
DECIMAL_LITERAL_RE = re.compile(r'Decimal\("([0-9.]+|Infinity)"\)')


def _decimal_literals_in_file(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {m.group(1) for m in DECIMAL_LITERAL_RE.finditer(text)}


def _present_in_matrix(value: str, matrix_text: str) -> bool:
    if value == "Infinity":
        return True  # not a citable rate; sentinel only
    # Try raw, grouped (Indian and Western), and percentage forms.
    if value in matrix_text:
        return True
    # Drop trailing zeros after the decimal point (e.g. "0.20" → "0.2")
    if "." in value:
        trimmed = value.rstrip("0").rstrip(".")
        if trimmed and trimmed in matrix_text:
            return True
    # Indian grouping: "150000" → "1,50,000"
    try:
        n = int(value)
    except ValueError:
        n = None
    if n is not None:
        for grouping in (
            _indian_group(n),
            f"{n:,}",  # Western grouping
            str(n),
        ):
            if grouping and grouping in matrix_text:
                return True
        # Percentage representation: 0.05 → "5%"
    # Percentage form: 0.10 → "10%"
    if "." in value:
        try:
            f = float(value)
            pct_value = f * 100
            pct_str_int = f"{int(round(pct_value))}%"
            pct_str_decimal = f"{pct_value:g}%"
            if pct_str_int in matrix_text or pct_str_decimal in matrix_text:
                return True
        except ValueError:
            pass
    return False


def _indian_group(n: int) -> str:
    """Return Indian-grouped decimal representation, e.g. 150000 → '1,50,000'."""
    if n < 0:
        return "-" + _indian_group(-n)
    s = str(n)
    if len(s) <= 3:
        return s
    head = s[:-3]
    tail = s[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    parts.append(tail)
    return ",".join(parts)


def test_matrix_file_exists():
    assert MATRIX_PATH.is_file(), (
        f"docs/tax-rule-source-matrix.md must exist; expected at {MATRIX_PATH}"
    )


@pytest.mark.parametrize(
    "rules_file",
    sorted(p.name for p in RULES_DIR.glob("fy_*.py")),
)
def test_every_decimal_constant_is_cited_in_matrix(rules_file: str):
    matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
    literals = _decimal_literals_in_file(RULES_DIR / rules_file)
    assert literals, f"{rules_file} contains no Decimal literals — sanity check failed"

    undocumented = sorted(
        value for value in literals if not _present_in_matrix(value, matrix_text)
    )
    assert not undocumented, (
        f"{rules_file} has Decimal constants not cited in tax-rule-source-matrix.md: "
        f"{undocumented}. Add them to the matrix (with URL + retrieved date) before "
        f"shipping rule changes."
    )
