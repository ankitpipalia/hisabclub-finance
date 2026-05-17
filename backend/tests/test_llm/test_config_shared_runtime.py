from __future__ import annotations

from app.config import Settings


def test_settings_default_to_shared_text_runtime_when_env_is_absent(monkeypatch) -> None:
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_API_BASE", raising=False)
    monkeypatch.delenv("LOCAL_LLM_QWEN_HOST_API_BASE", raising=False)
    monkeypatch.delenv("LOCAL_LLM_TEXT_HOST_API_BASE", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_QWEN_MODEL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_TEXT_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_base_url.endswith(":8097/v1")
    assert settings.llm_model
    assert "8472" not in settings.llm_base_url


def test_settings_accept_shared_runtime_env_aliases(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_LLM_API_BASE", "http://127.0.0.1:8097/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "Qwen3.6-27B-Q5_K_S.gguf")
    monkeypatch.setenv("LOCAL_LLM_VISION_API_BASE", "http://127.0.0.1:8096/v1")
    monkeypatch.setenv("LOCAL_LLM_VISION_MODEL", "Qwen3-VL-8B-Instruct-Q4_K_M.gguf")

    settings = Settings(_env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:8097/v1"
    assert settings.llm_model == "Qwen3.6-27B-Q5_K_S.gguf"
    assert settings.llm_vision_base_url == "http://127.0.0.1:8096/v1"
    assert settings.llm_vision_model == "Qwen3-VL-8B-Instruct-Q4_K_M.gguf"


def test_settings_accept_llm_ocr_base_url_alias(monkeypatch) -> None:
    monkeypatch.setenv("LLM_OCR_BASE_URL", "http://127.0.0.1:8095/v1")

    settings = Settings(_env_file=None)

    assert settings.ocr_base_url == "http://127.0.0.1:8095/v1"
