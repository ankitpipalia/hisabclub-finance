"""Model routing helpers for local LLM workloads."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class DifficultyScore:
    score: float
    level: str  # low | medium | high
    reason: str


def score_statement_difficulty(*, text: str, page_count: int) -> DifficultyScore:
    # Lightweight deterministic scorer; avoids extra model invocation.
    normalized = text or ""
    char_count = len(normalized)
    line_count = normalized.count("\n") + 1
    noisy_chars = sum(1 for ch in normalized if ch in {"|", "~", "`", "\x0c"})
    noise_ratio = (noisy_chars / max(1, char_count)) * 100

    score = 0.0
    score += min(4.0, page_count / 4.0)
    score += min(3.0, char_count / 14000.0)
    score += min(2.0, line_count / 1200.0)
    score += min(1.5, noise_ratio / 3.0)

    if score < 3.5:
        return DifficultyScore(score=score, level="low", reason="short_clean_document")
    if score < 6.5:
        return DifficultyScore(score=score, level="medium", reason="moderate_layout_complexity")
    return DifficultyScore(score=score, level="high", reason="long_or_noisy_document")


def route_model_for_task(
    *,
    task: str,
    difficulty: DifficultyScore | None = None,
) -> str:
    base = settings.llm_model
    if not settings.llm_router_enabled:
        return base

    small = settings.llm_small_model or base
    large = settings.llm_large_model or base

    if task in {
        "statement_classification",
        "transfer_classification",
        "document_classification",
    }:
        return small

    if difficulty is None:
        return base
    if difficulty.level == "high":
        return large
    if difficulty.level == "low":
        return small
    return base
