"""LLM client — calls OpenAI-compatible chat/completions endpoint."""

from __future__ import annotations

import base64
import json
import logging
import time
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class _CircuitBreaker:
    def __init__(self, *, fail_threshold: int = 3, reset_timeout_sec: float = 60.0) -> None:
        self.fail_threshold = fail_threshold
        self.reset_timeout_sec = reset_timeout_sec
        self.failure_count = 0
        self.opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= self.reset_timeout_sec:
            self.failure_count = 0
            self.opened_at = None
            return True
        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.fail_threshold:
            self.opened_at = time.monotonic()


_CIRCUITS_BY_BASE_URL: dict[str, _CircuitBreaker] = {}


class LLMClient:
    """Async client for OpenAI-compatible LLM endpoints (e.g. llama-server)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._validate_local_only()
        self._circuit = _CIRCUITS_BY_BASE_URL.setdefault(
            self.base_url,
            _CircuitBreaker(),
        )

    def _validate_local_only(self) -> None:
        if not settings.local_only_mode:
            return
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        if host not in settings.parsed_local_llm_hosts():
            raise ValueError(
                "Local-only mode is enabled. LLM base URL must use a local host "
                f"({sorted(settings.parsed_local_llm_hosts())}), got '{host}'."
            )

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.1,
        timeout_sec: float | None = None,
        max_attempts: int | None = None,
        model: str | None = None,
        response_format: dict | None = None,
        extra_body: dict | None = None,
    ) -> str:
        """Send a chat completion request and return the assistant's reply text.

        Handles timeouts, retries (up to 2), and errors gracefully.
        Returns empty string on failure rather than raising.
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # Qwen-family models on llama.cpp can emit reasoning_content by default. Disable
            # thinking mode so downstream finance prompts receive a final answer
            # in message.content.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if response_format:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)

        return await self._send_chat_request(
            payload=payload,
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
        )

    async def chat_vision(
        self,
        prompt: str,
        *,
        image_bytes: bytes,
        image_media_type: str = "image/png",
        max_tokens: int = 2800,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
        max_attempts: int | None = None,
        model: str | None = None,
    ) -> str:
        data_url = _image_bytes_to_data_url(image_bytes, image_media_type)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        return await self._send_chat_request(
            payload=payload,
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
        )

    async def chat_vision_json(
        self,
        prompt: str,
        *,
        image_bytes: bytes,
        image_media_type: str = "image/png",
        schema: dict | None = None,
        max_tokens: int = 2800,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
        max_attempts: int | None = None,
        model: str | None = None,
    ) -> dict | None:
        data_url = _image_bytes_to_data_url(image_bytes, image_media_type)
        response_format: dict | None = None
        if settings.llm_json_mode:
            if schema:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "finance_statement_vision_extraction",
                        "schema": schema,
                    },
                }
            else:
                response_format = {"type": "json_object"}

        payload = {
            "model": model or self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if response_format:
            payload["response_format"] = response_format

        text = await self._send_chat_request(
            payload=payload,
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
        )
        if not text:
            return None
        cleaned = _clean_json_text(text)
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.warning("LLM vision JSON decode failed for payload prefix=%s", cleaned[:180])
        return None

    async def _send_chat_request(
        self,
        *,
        payload: dict,
        timeout_sec: float | None,
        max_attempts: int | None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        if not self._circuit.allow_request():
            logger.warning("LLM circuit is open for %s; skipping request.", self.base_url)
            return ""

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        safe_attempts = max(1, int(max_attempts or settings.llm_request_max_attempts))
        safe_timeout = max(5.0, float(timeout_sec or settings.llm_request_timeout_sec))
        last_error: Exception | None = None
        for attempt in range(safe_attempts):
            try:
                async with httpx.AsyncClient(timeout=safe_timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0]["message"]
                        content = msg.get("content") or ""
                        self._circuit.record_success()
                        return content.strip()
                    logger.warning("LLM returned no choices: %s", data)
                    self._circuit.record_failure()
                    return ""
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "LLM request timeout (attempt %d/%d): %s",
                    attempt + 1,
                    safe_attempts,
                    exc,
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    "LLM HTTP error %s (attempt %d/%d): %s",
                    exc.response.status_code,
                    attempt + 1,
                    safe_attempts,
                    exc,
                )
            except Exception as exc:
                last_error = exc
                logger.error(
                    "LLM unexpected error (attempt %d/%d): %s",
                    attempt + 1,
                    safe_attempts,
                    exc,
                )

        logger.error(
            "LLM request failed after %d attempts. Last error: %s",
            safe_attempts,
            last_error,
        )
        self._circuit.record_failure()
        return ""

    async def chat_json(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        max_tokens: int = 2200,
        temperature: float = 0.0,
        timeout_sec: float | None = None,
        max_attempts: int | None = None,
        model: str | None = None,
    ) -> dict | None:
        response_format: dict | None = None
        if settings.llm_json_mode:
            if schema:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "finance_statement_extraction",
                        "schema": schema,
                    },
                }
            else:
                response_format = {"type": "json_object"}

        text = await self.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
            model=model,
            response_format=response_format,
        )
        if not text:
            return None
        cleaned = _clean_json_text(text)
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.warning("LLM JSON decode failed for payload prefix=%s", cleaned[:180])
        return None

    def with_model(self, model: str) -> "LLMClient":
        return LLMClient(base_url=self.base_url, api_key=self.api_key, model=model)


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("<think>") and "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    candidate = _extract_json_candidate(cleaned)
    return candidate or cleaned


def _extract_json_candidate(text: str) -> str | None:
    starts = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
    if not starts:
        return None

    start = min(starts)
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1].strip()
    return None


def _image_bytes_to_data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
