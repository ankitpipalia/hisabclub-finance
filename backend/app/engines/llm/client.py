"""LLM client — calls OpenAI-compatible chat/completions endpoint."""

from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Async client for OpenAI-compatible LLM endpoints (e.g. llama-server)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._validate_local_only()

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
        url = f"{self.base_url}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # Qwen3.5 on llama.cpp emits reasoning_content by default. Disable
            # thinking mode so downstream finance prompts receive a final answer
            # in message.content.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if response_format:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)

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
                        return content.strip()
                    logger.warning("LLM returned no choices: %s", data)
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
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return cleaned
