"""Verify the snapshot helper's compare + update semantics."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_parser._snapshot import _to_jsonable, assert_matches_snapshot


def test_to_jsonable_serializes_decimal_as_string():
    payload = _to_jsonable({"amount": Decimal("1.50"), "nested": [Decimal("0.01")]})
    assert payload["amount"] == "1.50"
    assert payload["nested"] == ["0.01"]


def test_to_jsonable_serializes_dates_as_iso_strings():
    payload = _to_jsonable({"d": date(2026, 5, 1)})
    assert payload["d"] == "2026-05-01"


def test_snapshot_creates_file_when_absent(tmp_path: Path):
    target = tmp_path / "snap.json"
    assert_matches_snapshot({"name": "ok"}, target)
    assert target.exists()
    data = json.loads(target.read_text())
    assert data == {"name": "ok"}


def test_snapshot_passes_when_payload_matches(tmp_path: Path):
    target = tmp_path / "snap.json"
    target.write_text(json.dumps({"name": "ok"}, indent=2, sort_keys=True) + "\n")
    assert_matches_snapshot({"name": "ok"}, target)


def test_snapshot_fails_with_clear_message_on_diff(tmp_path: Path):
    target = tmp_path / "snap.json"
    target.write_text(json.dumps({"name": "ok"}, indent=2, sort_keys=True) + "\n")
    with pytest.raises(AssertionError) as exc:
        assert_matches_snapshot({"name": "changed"}, target)
    assert "Snapshot mismatch" in str(exc.value)
    assert "UPDATE_SNAPSHOTS=1" in str(exc.value)


def test_snapshot_update_env_rewrites_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "snap.json"
    target.write_text(json.dumps({"name": "old"}, indent=2, sort_keys=True) + "\n")
    monkeypatch.setenv("UPDATE_SNAPSHOTS", "1")
    assert_matches_snapshot({"name": "new"}, target)
    data = json.loads(target.read_text())
    assert data == {"name": "new"}
