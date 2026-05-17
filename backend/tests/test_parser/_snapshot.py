"""Tiny snapshot helper for per-bank parser regression tests.

Keeps an aggregated, non-PII shape on disk so reviews diff parser changes
cleanly. Decimals serialize as strings; UUIDs and dates as ISO strings.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def assert_matches_snapshot(actual: Any, snapshot_path: Path) -> None:
    """Compare `actual` to the JSON file at `snapshot_path`.

    Set UPDATE_SNAPSHOTS=1 to rewrite snapshots instead of asserting.
    """
    payload = json.dumps(_to_jsonable(actual), indent=2, sort_keys=True)
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(payload + "\n")
        return
    expected = snapshot_path.read_text().rstrip("\n")
    if payload != expected:
        raise AssertionError(
            f"Snapshot mismatch at {snapshot_path}.\n"
            f"Run with UPDATE_SNAPSHOTS=1 to refresh.\n\n"
            f"--- expected\n{expected[:1000]}\n--- actual\n{payload[:1000]}"
        )
