from __future__ import annotations

from app.config import settings
from app.engines.llm.vision_statement import llm_parse_statement_from_page_images


class _FakeVisionClient:
    async def chat_vision_json(self, prompt: str, *, image_bytes: bytes, **kwargs):  # noqa: ANN003
        return {
            "bank_name": "SBI",
            "account_type": "savings",
            "account_number_masked": "XXXX1234",
            "statement_period_start": "01/04/2025",
            "statement_period_end": "30/04/2025",
            "opening_balance": "1000.00",
            "closing_balance": "850.00",
            "transactions": [
                {
                    "tran_date": "05/04/2025",
                    "narration": "UPI PAYMENT",
                    "withdrawal_dr": "150.00",
                    "reference": "UPI/412345678901",
                    "confidence": 0.91,
                }
            ],
        }


async def _fake_render_pdf_pages(pdf_bytes: bytes, page_indexes: list[int], *, dpi: int):  # noqa: ANN001
    return [(idx, b"png-bytes") for idx in page_indexes[:1]]


async def test_llm_parse_statement_from_page_images(monkeypatch):
    monkeypatch.setattr(settings, "llm_vision_page_limit", 2)
    monkeypatch.setattr(
        "app.engines.llm.vision_statement.render_pdf_pages",
        lambda pdf_bytes, page_indexes, dpi: [(idx, b"png-bytes") for idx in page_indexes[:1]],
    )

    result = await llm_parse_statement_from_page_images(
        _FakeVisionClient(),
        b"%PDF-1.4",
        bank_hint="SBI",
        account_type_hint="bank_account",
    )

    assert result.statement is not None
    assert result.statement.bank_name == "SBI"
    assert result.statement.account_type == "savings"
    assert len(result.statement.transactions) == 1
    assert result.statement.transactions[0].reference_number == "UPI/412345678901"


async def test_llm_parse_statement_from_page_images_defaults_confidence(monkeypatch):
    class _NoConfidenceClient:
        async def chat_vision_json(self, prompt: str, *, image_bytes: bytes, **kwargs):  # noqa: ANN003
            return {
                "bank_name": "ICICI",
                "account_type": "savings",
                "transactions": [
                    {
                        "date": "20/04/2025",
                        "description": "UPI/rahul@upi/Payment",
                        "amount": "1250.00",
                        "direction": "debit",
                        "reference_number": "UPI/412345678901",
                    }
                ],
            }

    monkeypatch.setattr(settings, "llm_vision_page_limit", 1)
    monkeypatch.setattr(
        "app.engines.llm.vision_statement.render_pdf_pages",
        lambda pdf_bytes, page_indexes, dpi: [(0, b"png-bytes")],
    )

    result = await llm_parse_statement_from_page_images(
        _NoConfidenceClient(),
        b"%PDF-1.4",
        bank_hint="ICICI",
        account_type_hint="bank_account",
    )

    assert result.statement is not None
    assert len(result.statement.transactions) == 1
    assert result.statement.transactions[0].confidence >= 0.9
