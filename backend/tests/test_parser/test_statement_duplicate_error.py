"""Regression test for the concurrent-upload race fix in parser/base.py.

Two concurrent uploads of the same statement (matching user_id +
statement_fingerprint while is_active=true) both pass the pre-check, then race
on INSERT. The unique index `uq_statements_active_fingerprint` rejects the
second insert with an IntegrityError. The parser must translate that into a
StatementDuplicateError so the API surfaces a clean 4xx instead of a 500.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.engines.parser.base import (
    StatementDuplicateError,
    _is_statement_fingerprint_violation,
)


def _make_integrity_error(message: str) -> IntegrityError:
    orig = MagicMock()
    orig.__str__ = lambda self: message  # type: ignore[assignment]
    return IntegrityError("INSERT INTO statements ...", params=None, orig=orig)


def test_fingerprint_violation_detected_by_index_name():
    exc = _make_integrity_error(
        'duplicate key value violates unique constraint "uq_statements_active_fingerprint"'
    )
    assert _is_statement_fingerprint_violation(exc) is True


def test_fingerprint_violation_detected_by_column_name():
    exc = _make_integrity_error(
        "duplicate key value violates unique constraint on column statement_fingerprint"
    )
    assert _is_statement_fingerprint_violation(exc) is True


def test_unrelated_integrity_error_not_classified_as_duplicate():
    exc = _make_integrity_error(
        'null value in column "user_id" violates not-null constraint'
    )
    assert _is_statement_fingerprint_violation(exc) is False


def test_statement_duplicate_error_is_value_error_subclass():
    # The API layer catches ValueError to surface 4xx; ensure inheritance chain
    # holds so this remains true after refactors.
    assert issubclass(StatementDuplicateError, ValueError)
