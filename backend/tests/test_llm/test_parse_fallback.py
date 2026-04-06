from __future__ import annotations

import pytest

from app.config import settings
from app.engines.llm.parse_fallback import llm_parse_statement


class _FakeLLMClient:
    def __init__(self, payloads: list[dict | None]) -> None:
        self._payloads = payloads
        self.calls = 0

    async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
        idx = min(self.calls, len(self._payloads) - 1)
        self.calls += 1
        return self._payloads[idx]


@pytest.mark.asyncio
async def test_llm_parse_statement_iterative_merges_chunks(monkeypatch):
    monkeypatch.setattr(settings, "llm_iterative_chunk_chars", 1500)
    monkeypatch.setattr(settings, "llm_iterative_overlap_lines", 1)
    monkeypatch.setattr(settings, "llm_max_chunk_count", 4)

    payload_1 = {
        "bank_name": "HDFC",
        "account_type": "credit_card",
        "account_number_masked": "XX1234",
        "statement_period_start": "2026-02-01",
        "statement_period_end": "2026-02-28",
        "opening_balance": 10000.0,
        "closing_balance": 8500.0,
        "transactions": [
            {
                "date": "2026-02-12",
                "description": "PAYMENT RECEIVED",
                "amount": 1500.0,
                "direction": "credit",
                "reference_number": "A1",
                "confidence": 0.92,
            }
        ],
    }
    payload_2 = {
        "bank_name": "HDFC",
        "account_type": "credit_card",
        "transactions": [
            {
                "date": "2026-02-14",
                "description": "AMAZON SELLER SERVICES",
                "amount": 1249.0,
                "direction": "debit",
                "reference_number": "A2",
                "confidence": 0.86,
            },
            # duplicate row from overlap should be deduped
            {
                "date": "2026-02-12",
                "description": "PAYMENT RECEIVED",
                "amount": 1500.0,
                "direction": "credit",
                "reference_number": "A1",
                "confidence": 0.92,
            },
        ],
    }
    client = _FakeLLMClient([payload_1, payload_2])
    lines = [f"line {i} " + ("x" * 48) for i in range(1, 70)]
    text = "\n".join(lines)

    result = await llm_parse_statement(
        client,  # type: ignore[arg-type]
        text,
        bank_hint="HDFC",
        account_type_hint="credit_card",
    )

    assert result is not None
    assert result.bank_name == "HDFC"
    assert result.account_type == "credit_card"
    assert result.account_number_masked == "XX1234"
    assert result.statement_period_start.isoformat() == "2026-02-01"
    assert result.statement_period_end.isoformat() == "2026-02-28"
    assert len(result.transactions) == 2
    assert client.calls >= 2


@pytest.mark.asyncio
async def test_llm_parse_statement_returns_none_when_no_txns(monkeypatch):
    monkeypatch.setattr(settings, "llm_iterative_chunk_chars", 500)
    client = _FakeLLMClient([{"account_type": "savings", "transactions": []}])
    result = await llm_parse_statement(
        client,  # type: ignore[arg-type]
        "header\nsummary",
        bank_hint="AXIS",
        account_type_hint="bank_account",
    )
    assert result is None


@pytest.mark.asyncio
async def test_llm_parse_statement_uses_tier2_table_mapping():
    # First chat_json call is used for column mapping.
    client = _FakeLLMClient(
        [
            {
                "date_col": 0,
                "description_col": 1,
                "debit_col": 2,
                "credit_col": 3,
                "amount_col": None,
                "direction_col": None,
                "reference_col": 4,
            }
        ]
    )
    table_rows = [
        "Date | Description | Debit | Credit | Ref",
        "12/03/2026 | UPI/DR/123/PHONEPE | 850.00 |  | 123",
        "12/03/2026 | UPI REVERSAL |  | 850.00 | 124",
    ]
    result = await llm_parse_statement(
        client,  # type: ignore[arg-type]
        "unused full text",
        bank_hint="AXIS",
        account_type_hint="bank_account",
        table_rows=table_rows,
    )

    assert result is not None
    assert result.parser_id == "llm_tier2_column_map"
    assert len(result.transactions) == 2
    assert result.transactions[0].direction == "debit"
    assert result.transactions[1].direction == "credit"


@pytest.mark.asyncio
async def test_llm_parse_statement_drops_invalid_rows_without_losing_valid_rows(monkeypatch):
    monkeypatch.setattr(settings, "llm_iterative_chunk_chars", 1200)
    client = _FakeLLMClient(
        [
            {
                "bank_name": "ICICI",
                "account_type": "savings",
                "transactions": [
                    {
                        "date": "03/04/2025",
                        "description": "TELE TRANSFER CREDIT 504321987654",
                        "amount": "45000.00",
                        "direction": "credit",
                        "reference_number": "504321987654",
                        "confidence": 0.84,
                    },
                    {
                        "date": "not-a-date",
                        "description": "broken row",
                        "amount": 50,
                        "direction": "debit",
                    },
                ],
            }
        ]
    )

    result = await llm_parse_statement(
        client,  # type: ignore[arg-type]
        "03/04/2025 TELE TRANSFER CREDIT 504321987654 45000.00",
        bank_hint="ICICI",
        account_type_hint="bank_account",
    )

    assert result is not None
    assert len(result.transactions) == 1
    assert result.transactions[0].reference_number == "504321987654"
