from __future__ import annotations

import json

import pytest

from app.engines.jobs.parser_state import ParserStage, advance_stage, job_key, load_job_state


@pytest.mark.asyncio
async def test_parser_state_advances_and_loads(monkeypatch):
    store = {}

    async def _fake_redis(_url, *parts):
        command = parts[0]
        key = parts[1]
        if command == "GET":
            return store.get(key)
        if command == "SET":
            store[key] = parts[2].encode("utf-8")
            return "OK"
        raise AssertionError(command)

    monkeypatch.setattr("app.engines.jobs.parser_state._redis_command", _fake_redis)

    state = await advance_stage("job-1", ParserStage.EXTRACTING, text_pages=2)
    loaded = await load_job_state("job-1")

    assert job_key("job-1") in store
    assert state["stage"] == "extracting"
    assert loaded == {"stage": "extracting", "text_pages": 2}
    assert json.loads(store[job_key("job-1")].decode("utf-8"))["stage"] == "extracting"
