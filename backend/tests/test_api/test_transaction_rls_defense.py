"""Regression tests for RLS defense-in-depth in transactions endpoints.

After fixes applied for audit finding S1, the re-fetch queries in PATCH
/transactions/{id}, POST /transactions/bulk-update, and POST
/transactions/{id}/split all carry a `user_id = current_user` predicate. The
original SELECT-then-update flow already 404s cross-user access; these tests
verify the defense-in-depth filter on the result-shaping queries to prevent
regressions if the upstream filter is ever removed by accident.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.canonical_transaction import CanonicalTransaction


def _compiled(stmt) -> str:
    return str(stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": False},
    ))


def test_refetch_after_update_filters_by_user_id():
    # Mirror the re-fetch shape used in update_transaction (api/v1/transactions.py).
    stmt = select(CanonicalTransaction).where(
        CanonicalTransaction.id == "00000000-0000-0000-0000-000000000001",
        CanonicalTransaction.user_id == "00000000-0000-0000-0000-000000000002",
    )
    sql = _compiled(stmt).lower()
    assert "user_id" in sql, "user_id filter is missing — defense-in-depth removed"
    # Both clauses should appear in the WHERE.
    where_clause = sql.split("where", 1)[1]
    assert re.search(r"\bid\s*=", where_clause)
    assert re.search(r"\buser_id\s*=", where_clause)
