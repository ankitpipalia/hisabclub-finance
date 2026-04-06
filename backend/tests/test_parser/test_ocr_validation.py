from __future__ import annotations

from datetime import date

import pytest

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.parser.base import ExtractedTransaction
from app.engines.parser.ocr import assess_text_quality, extract_text_with_ocr_fallback
from app.engines.parser.validation import validate_extracted_transactions


class _FakeVisionClient(LLMClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    async def chat_vision(self, prompt: str, *, image_bytes: bytes, **kwargs):  # noqa: ANN003
        self.calls.append((prompt, image_bytes))
        return "01/04/2025 PAYMENT RECEIVED 1500.00 CR"


def test_assess_text_quality_flags_low_signal_pages() -> None:
    result = assess_text_quality(
        [
            "",
            "12345 67890",
            "valid text with enough words to clearly exceed the minimum signal threshold",
        ]
    )
    assert result.should_ocr is True
    assert result.empty_pages == 1
    assert result.low_signal_pages == [0, 1]


@pytest.mark.asyncio
async def test_extract_text_with_ocr_fallback_replaces_low_signal_pages(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_page_limit", 5)
    monkeypatch.setattr(
        "app.engines.parser.ocr.render_pdf_pages",
        lambda pdf_bytes, page_indexes, dpi: [(idx, b"png-bytes") for idx in page_indexes],
    )
    client = _FakeVisionClient()

    result = await extract_text_with_ocr_fallback(
        pdf_bytes=b"%PDF-1.4",
        text_pages=["", "clear page text with enough characters to avoid OCR replacement"],
        client=client,
    )

    assert result.used_ocr is True
    assert "PAYMENT RECEIVED" in result.pages[0]
    assert result.pages[1] == "clear page text with enough characters to avoid OCR replacement"
    assert len(client.calls) == 1


def test_validate_extracted_transactions_drops_duplicates_and_out_of_range_rows() -> None:
    txns = [
        ExtractedTransaction(
            transaction_date=date(2025, 4, 10),
            posting_date=None,
            description="UPI PAYMENT",
            amount=850.0,
            direction="debit",
            confidence=0.8,
        ),
        ExtractedTransaction(
            transaction_date=date(2025, 4, 10),
            posting_date=None,
            description="UPI PAYMENT",
            amount=850.0,
            direction="debit",
            confidence=0.8,
        ),
        ExtractedTransaction(
            transaction_date=date(2024, 1, 1),
            posting_date=None,
            description="OLD ROW",
            amount=100.0,
            direction="debit",
            confidence=0.9,
        ),
    ]

    result = validate_extracted_transactions(
        txns,
        statement_period_start=date(2025, 4, 1),
        statement_period_end=date(2025, 4, 30),
    )

    assert len(result.transactions) == 1
    assert result.dropped_count == 2
    assert result.warnings
