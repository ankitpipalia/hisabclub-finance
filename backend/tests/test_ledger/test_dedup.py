from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.engines.ledger.dedup import DedupEngine


class _ParsedTxn:
    def __init__(self) -> None:
        self.dedupe_fingerprint = None
        self.transaction_date = date(2025, 4, 3)
        self.amount = Decimal("1500.00")
        self.description_raw = "UPI PAYMENT HDFC CARD"
        self.reference_number = "123456789012"
        self.direction = "debit"
        self.id = uuid.uuid4()


@pytest.mark.asyncio
async def test_find_duplicate_passes_account_masked_into_fingerprint(monkeypatch) -> None:
    engine = DedupEngine()
    seen: dict[str, object] = {}

    def _fake_build(**kwargs):  # noqa: ANN003
        seen.update(kwargs)
        return "fp"

    async def _fake_match_by_fingerprint(db, user_id, fingerprint):  # noqa: ANN001, ANN201
        return None

    async def _fake_match_by_reference(db, user_id, parsed_txn, account_masked):  # noqa: ANN001, ANN201
        seen["reference_account_masked"] = account_masked
        return None

    async def _fake_match_by_amount_date_desc(db, user_id, parsed_txn, account_masked):  # noqa: ANN001, ANN201
        seen["desc_account_masked"] = account_masked
        return None, 0.0

    async def _fake_match_by_amount_date_window(db, user_id, parsed_txn, account_masked):  # noqa: ANN001, ANN201
        seen["window_account_masked"] = account_masked
        return None, 0.0

    monkeypatch.setattr(
        "app.engines.ledger.dedup.build_transaction_dedupe_fingerprint",
        _fake_build,
    )
    monkeypatch.setattr(engine, "_match_by_fingerprint", _fake_match_by_fingerprint)
    monkeypatch.setattr(engine, "_match_by_reference", _fake_match_by_reference)
    monkeypatch.setattr(engine, "_match_by_amount_date_desc", _fake_match_by_amount_date_desc)
    monkeypatch.setattr(engine, "_match_by_amount_date_window", _fake_match_by_amount_date_window)

    await engine.find_duplicate(
        db=None,  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        parsed_txn=_ParsedTxn(),  # type: ignore[arg-type]
        account_masked="XX1234",
    )

    assert seen["account_masked"] == "XX1234"
    assert seen["reference_account_masked"] == "XX1234"
    assert seen["desc_account_masked"] == "XX1234"
    assert seen["window_account_masked"] == "XX1234"
