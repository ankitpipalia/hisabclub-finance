from __future__ import annotations

import pytest

from app.engines.llm.client import LLMClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
        _FakeAsyncClient.captured = {
            "url": url,
            "json": json,
            "headers": headers,
        }
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "OK",
                        }
                    }
                ]
            }
        )


@pytest.mark.asyncio
async def test_llm_client_disables_thinking_mode(monkeypatch):
    from app.engines.llm import client as llm_client_module

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = LLMClient(
        base_url="http://localhost:8094/v1",
        api_key="",
        model="Qwen3.5-27B-Q3_K_M.gguf",
    )
    result = await client.chat(
        messages=[{"role": "user", "content": "test"}],
        max_tokens=16,
        max_attempts=1,
    )

    assert result == "OK"
    assert _FakeAsyncClient.captured["url"] == "http://localhost:8094/v1/chat/completions"
    assert _FakeAsyncClient.captured["json"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }


@pytest.mark.asyncio
async def test_llm_client_chat_json_sets_response_format(monkeypatch):
    from app.engines.llm import client as llm_client_module

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = LLMClient(
        base_url="http://localhost:8094/v1",
        api_key="",
        model="Qwen3.5-27B-Q3_K_M.gguf",
    )

    payload = await client.chat_json(
        messages=[{"role": "user", "content": "test"}],
        schema={
            "type": "object",
            "properties": {"ok": {"type": "string"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    )

    assert payload is None or isinstance(payload, dict)
    assert _FakeAsyncClient.captured["json"]["response_format"]["type"] in {
        "json_object",
        "json_schema",
    }
