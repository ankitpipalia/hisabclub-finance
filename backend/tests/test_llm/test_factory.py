from __future__ import annotations

from app.config import settings
from app.engines.llm.factory import (
    build_ocr_client,
    resolve_target_for_task,
    should_use_primary_vision_statement_parse,
    should_use_vision_for_statement_extraction,
)
from app.engines.llm.router import DifficultyScore


def test_resolve_target_for_task_uses_vision_endpoint_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_vision_enabled", True)
    monkeypatch.setattr(settings, "llm_vision_base_url", "http://localhost:8096/v1")
    monkeypatch.setattr(settings, "llm_vision_api_key", "vision-key")
    monkeypatch.setattr(settings, "llm_vision_model", "Qwen3-VL-8B-Q4_K_M.gguf")

    target = resolve_target_for_task(
        task="statement_extraction",
        difficulty=DifficultyScore(score=8.0, level="high", reason="complex"),
        prefer_vision=True,
    )

    assert target.mode == "vision"
    assert target.base_url == "http://localhost:8096/v1"
    assert target.api_key == "vision-key"
    assert target.model == "Qwen3-VL-8B-Q4_K_M.gguf"


def test_resolve_target_for_task_uses_text_router_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:8472/v1")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "base-model.gguf")
    monkeypatch.setattr(settings, "llm_small_model", "small-model.gguf")
    monkeypatch.setattr(settings, "llm_large_model", "large-model.gguf")
    monkeypatch.setattr(settings, "llm_vision_enabled", False)

    target = resolve_target_for_task(
        task="document_classification",
        difficulty=DifficultyScore(score=1.0, level="low", reason="simple"),
    )

    assert target.mode == "text"
    assert target.base_url == "http://localhost:8472/v1"
    assert target.model == "small-model.gguf"


def test_build_ocr_client_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_enabled", False)
    assert build_ocr_client() is None


def test_should_use_vision_for_statement_extraction(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_vision_enabled", True)
    monkeypatch.setattr(settings, "llm_vision_statement_extraction_enabled", True)

    assert should_use_vision_for_statement_extraction(prefer_llm=True, used_ocr=False) is True
    assert should_use_vision_for_statement_extraction(prefer_llm=False, used_ocr=True) is True

    monkeypatch.setattr(settings, "llm_vision_statement_extraction_enabled", False)
    assert should_use_vision_for_statement_extraction(prefer_llm=True, used_ocr=True) is False


def test_should_use_primary_vision_statement_parse(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_vision_enabled", True)
    monkeypatch.setattr(settings, "llm_vision_statement_extraction_enabled", True)
    monkeypatch.setattr(settings, "llm_vision_statement_primary", True)

    assert should_use_primary_vision_statement_parse() is True

    monkeypatch.setattr(settings, "llm_vision_statement_primary", False)
    assert should_use_primary_vision_statement_parse() is False
