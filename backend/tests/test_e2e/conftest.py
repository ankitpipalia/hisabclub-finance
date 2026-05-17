"""End-to-end harness against the user's real FY data folder.

Gated behind RUN_REAL_E2E=1 because this test suite touches real PII (bank
statements, tax filings, demat exports). Never runs in CI — the source data
lives on the developer's host.

Required env to opt in:
  RUN_REAL_E2E=1
  HISABCLUB_E2E_FOLDER=/path/to/FY24-25-Ankit-details   (defaults to that path)
  DATABASE_URL=postgresql+asyncpg://...                  (or settings default)

Optional:
  HISABCLUB_E2E_PASSWORD_MAP={"hdfc_statement.pdf": "secret"}  # JSON dict
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

DEFAULT_FOLDER = "/home/ankit/Documents/FY24-25-Ankit-details"


def pytest_collection_modifyitems(config, items):
    """Skip everything under test_e2e/ unless RUN_REAL_E2E=1 is set."""
    if os.environ.get("RUN_REAL_E2E") == "1":
        return
    skip_marker = pytest.mark.skip(
        reason="real-data E2E tests; set RUN_REAL_E2E=1 to enable (local only).",
    )
    for item in items:
        if "test_e2e" in str(item.fspath):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def real_data_root() -> Path:
    folder = os.environ.get("HISABCLUB_E2E_FOLDER", DEFAULT_FOLDER)
    path = Path(folder)
    if not path.exists() or not path.is_dir():
        pytest.skip(f"Real data folder not present at {folder}")
    return path


@pytest.fixture(scope="session")
def password_map() -> dict[str, str]:
    raw = os.environ.get("HISABCLUB_E2E_PASSWORD_MAP")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        pytest.fail(f"HISABCLUB_E2E_PASSWORD_MAP is not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        pytest.fail("HISABCLUB_E2E_PASSWORD_MAP must be a JSON object.")
    return {str(k): str(v) for k, v in parsed.items()}


@pytest_asyncio.fixture
async def e2e_db_session():
    """Open a SQLAlchemy session against the configured DATABASE_URL.

    Apply RLS context for a fresh per-test user so the import path can write
    canonical rows under realistic security constraints.
    """
    from app.database import async_session_factory
    from app.security.tenant_context import set_request_user_context

    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        try:
            await set_request_user_context(session, user_id)
        except Exception:
            # Older codepaths may use a different setter; the import attempt
            # above is the discovery probe. Skip cleanly if not available.
            pytest.skip("RLS context setter unavailable in this environment.")
        yield session, user_id
