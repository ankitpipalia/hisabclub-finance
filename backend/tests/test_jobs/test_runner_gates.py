from __future__ import annotations

from types import SimpleNamespace

from app.engines.jobs.runner import _apply_post_parse_gates


def test_apply_post_parse_gates_moves_to_review_required_on_low_yield(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "min_yield_rate_for_auto_promotion", 0.8)
    monkeypatch.setattr(settings, "require_cc_integrity_ok_for_auto_promotion", False)

    statement = SimpleNamespace(
        quarantined_row_count=0,
        expected_row_count=20,
        yield_rate=0.45,
        parse_status="parsed",
        parse_errors=None,
        account_type="savings",
    )
    gates = _apply_post_parse_gates(statement=statement, integrity=None)

    assert gates["yield_rate_ok"] is False
    assert statement.parse_status == "review_required"

