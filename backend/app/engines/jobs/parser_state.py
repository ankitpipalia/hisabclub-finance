from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.extraction_job import ExtractionJob

logger = logging.getLogger(__name__)


class ParserStage(str, Enum):
    QUEUED = "queued"
    DECRYPTING = "decrypting"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    DEDUPING = "deduping"
    BALANCE_CHECK = "balance_check"
    PROMOTING = "promoting"
    REVIEW_GATE = "review_gate"
    COMPLETE = "complete"
    FAILED = "failed"
    PARTIAL = "partial"


JOB_TTL_SECONDS = 86_400


def job_key(job_id: str) -> str:
    return f"parserjob:{job_id}"


async def save_job_state(
    job_id: str, state: dict[str, Any], *, redis_url: str | None = None
) -> None:
    payload = json.dumps(_json_safe(state), separators=(",", ":"))
    await _redis_command(
        redis_url or settings.redis_url, "SET", job_key(job_id), payload, "EX", str(JOB_TTL_SECONDS)
    )


async def load_job_state(job_id: str, *, redis_url: str | None = None) -> dict[str, Any] | None:
    raw = await _redis_command(redis_url or settings.redis_url, "GET", job_key(job_id))
    if raw in {None, b""}:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(str(raw))


async def advance_stage(
    job_id: str,
    stage: ParserStage,
    *,
    redis_url: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    state = await load_job_state(job_id, redis_url=redis_url) or {}
    state.update({"stage": stage.value, **extra})
    await save_job_state(job_id, state, redis_url=redis_url)
    return state


async def record_parser_stage(
    *,
    db: AsyncSession,
    job: ExtractionJob,
    stage: ParserStage,
    **extra: Any,
) -> None:
    job.current_stage = stage.value
    await db.flush()
    state = {
        "stage": stage.value,
        "job_id": str(job.id),
        "user_id": str(job.user_id),
        "raw_pdf_id": str(job.raw_pdf_id),
        **extra,
    }
    try:
        await advance_stage(str(job.id), stage, **state)
    except Exception as exc:  # Redis state should not break DB-backed jobs.
        logger.warning("Could not write parser job state to Redis for job %s: %s", job.id, exc)


async def _redis_command(redis_url: str, *parts: str) -> Any:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(_encode_resp(parts))
        await writer.drain()
        return await asyncio.wait_for(_read_resp(reader), timeout=2.0)
    finally:
        writer.close()
        await writer.wait_closed()


def _encode_resp(parts: tuple[str, ...]) -> bytes:
    out = [f"*{len(parts)}\r\n".encode("utf-8")]
    for part in parts:
        encoded = str(part).encode("utf-8")
        out.append(f"${len(encoded)}\r\n".encode("utf-8"))
        out.append(encoded + b"\r\n")
    return b"".join(out)


async def _read_resp(reader: asyncio.StreamReader) -> Any:
    prefix = await reader.readexactly(1)
    if prefix == b"+":
        return (await reader.readline()).rstrip(b"\r\n").decode("utf-8")
    if prefix == b"-":
        message = (await reader.readline()).rstrip(b"\r\n").decode("utf-8")
        raise RuntimeError(message)
    if prefix == b":":
        return int((await reader.readline()).rstrip(b"\r\n"))
    if prefix == b"$":
        length = int((await reader.readline()).rstrip(b"\r\n"))
        if length == -1:
            return None
        payload = await reader.readexactly(length)
        await reader.readexactly(2)
        return payload
    if prefix == b"*":
        count = int((await reader.readline()).rstrip(b"\r\n"))
        return [await _read_resp(reader) for _ in range(count)]
    raise RuntimeError(f"Unsupported Redis response prefix: {prefix!r}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
