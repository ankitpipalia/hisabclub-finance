"""Factory helpers for routed local LLM clients."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.engines.llm.client import LLMClient
from app.engines.llm.router import DifficultyScore, route_model_for_task


@dataclass(frozen=True)
class LLMTarget:
    task: str
    mode: str  # text | vision | ocr
    base_url: str
    api_key: str
    model: str
    reason: str


def build_client_for_task(
    *,
    task: str,
    difficulty: DifficultyScore | None = None,
    prefer_vision: bool = False,
) -> tuple[LLMClient, LLMTarget]:
    target = resolve_target_for_task(
        task=task,
        difficulty=difficulty,
        prefer_vision=prefer_vision,
    )
    return (
        LLMClient(
            base_url=target.base_url,
            api_key=target.api_key,
            model=target.model,
        ),
        target,
    )


def build_ocr_client() -> tuple[LLMClient, LLMTarget] | None:
    if not settings.ocr_enabled:
        return None
    target = LLMTarget(
        task="ocr_transcription",
        mode="ocr",
        base_url=settings.ocr_base_url,
        api_key=settings.ocr_api_key,
        model=settings.ocr_model,
        reason="ocr_endpoint",
    )
    return (
        LLMClient(
            base_url=target.base_url,
            api_key=target.api_key,
            model=target.model,
        ),
        target,
    )


def resolve_target_for_task(
    *,
    task: str,
    difficulty: DifficultyScore | None = None,
    prefer_vision: bool = False,
) -> LLMTarget:
    routed_model = route_model_for_task(task=task, difficulty=difficulty)
    if prefer_vision and settings.llm_vision_enabled:
        return LLMTarget(
            task=task,
            mode="vision",
            base_url=settings.llm_vision_base_url_resolved(),
            api_key=settings.llm_vision_api_key_resolved(),
            model=settings.llm_vision_model_resolved(),
            reason="vision_route_enabled",
        )

    return LLMTarget(
        task=task,
        mode="text",
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=routed_model,
        reason="default_text_route",
    )


def should_use_vision_for_statement_extraction(*, prefer_llm: bool, used_ocr: bool) -> bool:
    if not settings.llm_enabled or not settings.llm_vision_enabled:
        return False
    if not settings.llm_vision_statement_extraction_enabled:
        return False
    return prefer_llm or used_ocr


def should_use_primary_vision_statement_parse() -> bool:
    return (
        settings.llm_enabled
        and settings.llm_vision_enabled
        and settings.llm_vision_statement_extraction_enabled
        and settings.llm_vision_statement_primary
    )
