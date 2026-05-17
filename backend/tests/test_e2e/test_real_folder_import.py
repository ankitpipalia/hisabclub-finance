"""Full FY24-25 folder import smoke test against the user's real archive.

Skipped unless RUN_REAL_E2E=1 (see conftest.py). When enabled, runs the same
folder_importer path the manual `backend/scripts/import_folder_for_user.py`
uses, then asserts headline aggregates so regressions in classification or
parsing produce a clear failure.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_real_folder_imports_cleanly(e2e_db_session, real_data_root, password_map):
    from app.engines.intake.folder_importer import import_folder

    db, user_id = e2e_db_session
    result = await import_folder(
        db=db,
        user_id=user_id,
        folder_path=str(real_data_root),
        parse_supported=True,
        dry_run=False,
        force_reprocess=True,
        password_map=password_map or None,
    )

    assert result.discovered >= 30, (
        f"Expected ≥30 files discovered, got {result.discovered}. "
        "Folder structure may have changed."
    )
    assert result.failed == 0, (
        f"{result.failed} files failed to import. Messages: {result.messages[-10:]}"
    )

    by_type = result.by_doc_type
    # Coarse coverage — exact counts drift as the user adds documents.
    assert by_type.get("bank_statement", 0) >= 1, "Expected at least one bank statement"
    assert any(
        by_type.get(key, 0) >= 1 for key in ("form16", "tax_form16", "form_16")
    ), "Expected at least one Form-16"
    assert any(
        by_type.get(key, 0) >= 1
        for key in ("demat_holdings", "demat_statement", "demat")
    ), "Expected at least one demat holding/statement"
