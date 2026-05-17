"""Correction-chat skip reasons surface specific failure modes.

Audit C8: an LLM-proposed action that fails validation (unknown category,
disallowed nature, empty notes) used to be silently dropped. The plan now
requires each skip to carry a human-readable reason so the user sees why their
correction wasn't applied.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.engines.llm.correction_chat import _plan_action


def _txn() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        category_id=None,
        transaction_nature="expense",
        notes=None,
        is_excluded=False,
    )


def test_unknown_category_returns_skip_reason():
    planned = _plan_action(
        action="set_category",
        raw={"category_name": "ImaginaryBucket"},
        txn=_txn(),
        category_by_name={},
    )
    assert planned is not None
    assert "_skip_reason" in planned
    assert "ImaginaryBucket" in planned["_skip_reason"]


def test_missing_category_name_returns_skip_reason():
    planned = _plan_action(
        action="set_category",
        raw={},
        txn=_txn(),
        category_by_name={},
    )
    assert planned is not None
    assert "_skip_reason" in planned
    assert "Missing" in planned["_skip_reason"]


def test_disallowed_nature_returns_skip_reason():
    planned = _plan_action(
        action="set_nature",
        raw={"transaction_nature": "imaginary_kind"},
        txn=_txn(),
        category_by_name={},
    )
    assert planned is not None
    assert "_skip_reason" in planned
    assert "imaginary_kind" in planned["_skip_reason"]


def test_empty_notes_returns_skip_reason():
    planned = _plan_action(
        action="set_notes",
        raw={"notes": "   "},
        txn=_txn(),
        category_by_name={},
    )
    assert planned is not None
    assert "_skip_reason" in planned


def test_valid_nature_returns_plan_without_skip():
    planned = _plan_action(
        action="set_nature",
        raw={"transaction_nature": "income"},
        txn=_txn(),
        category_by_name={},
    )
    assert planned is not None
    assert "_skip_reason" not in planned
    assert planned["after"] == "income"
