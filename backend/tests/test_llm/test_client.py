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


class _FailingAsyncClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> _FailingAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
        _FailingAsyncClient.calls += 1
        raise RuntimeError("endpoint down")


_FailingAsyncClient.calls = 0


@pytest.mark.asyncio
async def test_llm_client_disables_thinking_mode(monkeypatch):
    from app.engines.llm import client as llm_client_module

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = LLMClient(
        base_url="http://localhost:8097/v1",
        api_key="",
        model="Qwen3.6-27B-Q5_K_S.gguf",
    )
    result = await client.chat(
        messages=[{"role": "user", "content": "test"}],
        max_tokens=16,
        max_attempts=1,
    )

    assert result == "OK"
    assert _FakeAsyncClient.captured["url"] == "http://localhost:8097/v1/chat/completions"
    assert _FakeAsyncClient.captured["json"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }


@pytest.mark.asyncio
async def test_llm_client_circuit_breaker_skips_open_endpoint(monkeypatch):
    from app.engines.llm import client as llm_client_module

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", _FailingAsyncClient)
    _FailingAsyncClient.calls = 0

    client = LLMClient(
        base_url="http://localhost:18097/v1",
        api_key="",
        model="Qwen3.6-27B-Q5_K_S.gguf",
    )
    for _ in range(3):
        assert await client.chat([{"role": "user", "content": "test"}], max_attempts=1) == ""

    assert await client.chat([{"role": "user", "content": "test"}], max_attempts=1) == ""
    assert _FailingAsyncClient.calls == 3


@pytest.mark.asyncio
async def test_llm_client_chat_json_sets_response_format(monkeypatch):
    from app.engines.llm import client as llm_client_module

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = LLMClient(
        base_url="http://localhost:8097/v1",
        api_key="",
        model="Qwen3.6-27B-Q5_K_S.gguf",
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


@pytest.mark.asyncio
async def test_llm_client_chat_vision_json_sets_response_format(monkeypatch):
    from app.engines.llm import client as llm_client_module

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = LLMClient(
        base_url="http://localhost:8097/v1",
        api_key="",
        model="Qwen3-VL-8B-Q4_K_M.gguf",
    )

    payload = await client.chat_vision_json(
        "extract",
        image_bytes=b"png",
        schema={
            "type": "object",
            "properties": {"ok": {"type": "string"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        max_attempts=1,
    )

    assert payload is None or isinstance(payload, dict)
    content = _FakeAsyncClient.captured["json"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert _FakeAsyncClient.captured["json"]["response_format"]["type"] in {
        "json_object",
        "json_schema",
    }
