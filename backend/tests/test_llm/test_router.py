from __future__ import annotations

from app.config import settings
from app.engines.llm.router import route_model_for_task, score_statement_difficulty


def test_score_statement_difficulty_levels():
    low = score_statement_difficulty(text="short text", page_count=1)
    high = score_statement_difficulty(text=("x" * 60000), page_count=18)

    assert low.level in {"low", "medium"}
    assert high.level == "high"
    assert high.score > low.score


def test_route_model_for_task_prefers_small_for_classification(monkeypatch):
    monkeypatch.setattr(settings, "llm_router_enabled", True)
    monkeypatch.setattr(settings, "llm_model", "main-model")
    monkeypatch.setattr(settings, "llm_small_model", "small-model")
    monkeypatch.setattr(settings, "llm_large_model", "large-model")

    difficulty = score_statement_difficulty(text="x" * 30000, page_count=12)
    assert route_model_for_task(task="statement_classification", difficulty=difficulty) == "small-model"
    assert route_model_for_task(task="statement_extraction", difficulty=difficulty) in {
        "main-model",
        "large-model",
    }

