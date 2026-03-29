from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def publish_job_event(event: str, payload: dict) -> None:
    try:
        import redis.asyncio as redis  # type: ignore[import-not-found]
    except Exception:
        return

    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        await client.publish("jobs:events", json.dumps({"event": event, "payload": payload}))
        await client.aclose()
    except Exception as exc:
        logger.debug("Redis job event publish failed: %s", exc)
