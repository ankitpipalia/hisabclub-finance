"""LLM client — calls OpenAI-compatible chat/completions endpoint."""

from __future__ import annotations

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
        timeout_sec: float = 120.0,
        max_attempts: int = 3,
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
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        safe_attempts = max(1, max_attempts)
        last_error: Exception | None = None
        for attempt in range(safe_attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0]["message"]
                        content = msg.get("content") or ""
                        # For reasoning models (e.g. QWQ), the actual answer
                        # may be in "content" while chain-of-thought is in
                        # "reasoning_content". We return only "content".
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
