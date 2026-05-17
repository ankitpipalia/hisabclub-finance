"""Per-file smoke against the real FY24-25 archive.

Each file passes through classify_document so we get an explicit assertion
that the production classifier still resolves the doc_type the user expects.
This is parametrized over whatever files happen to be present so adding a
new bank statement to the folder automatically gets covered.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _discover_files(root_env: str = "HISABCLUB_E2E_FOLDER") -> list[Path]:
    folder = os.environ.get(root_env, "/home/ankit/Documents/FY24-25-Ankit-details")
    root = Path(folder)
    if not root.exists():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {".pdf", ".csv", ".xlsx", ".xls"}
    )


# Build the parametrization at collection time — pytest needs the list before
# the test starts. If the folder doesn't exist (or RUN_REAL_E2E is off), the
# conftest skip kicks in and these tests never collect anyway.
_FILES = _discover_files()


@pytest.mark.parametrize("path", _FILES, ids=[p.name for p in _FILES])
def test_each_real_file_has_resolvable_doc_type(path: Path):
    from app.engines.intake.doc_classifier import classify_document

    classified = classify_document(str(path))
    assert classified.doc_type, (
        f"{path.name} produced an empty doc_type. Classifier needs a rule "
        "for this filename pattern or content shape."
    )
    # Unknown is a valid label (the classifier signals it explicitly) — but
    # never a missing/None.
    assert classified.doc_type != "", path.name
