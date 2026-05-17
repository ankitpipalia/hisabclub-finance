import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.database import async_session_factory


def _resolve_frontend_dir() -> Path | None:
    configured = os.getenv("FRONTEND_DIST_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "frontend" / "dist",
            Path("/app/frontend/dist"),
            Path("/frontend/dist"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


FRONTEND_DIR = _resolve_frontend_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    worker_task: asyncio.Task | None = None
    if settings.job_runner_enabled:
        from app.engines.jobs.runner import run_worker_loop

        worker_id = f"embedded-worker-{os.getpid()}"
        worker_task = asyncio.create_task(
            run_worker_loop(
                worker_id=worker_id,
                poll_seconds=max(0.2, settings.job_runner_poll_seconds),
                enable_dlq_retry=settings.job_runner_dlq_retry_enabled,
            )
        )
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(
    title=settings.app_name,
    description="Privacy-first Indian personal finance ledger",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hisabclub-dev-web.ankit-tech.store",
        "https://hisabclub-dev-api.ankit-tech.store",
        "http://192.168.1.69:5276",
        "http://localhost:5276",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "database": "unavailable", "llm": "not_checked_at_boot"},
        ) from exc

    try:
        await _ping_redis(settings.redis_url)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "redis": "unavailable", "llm": "not_checked_at_boot"},
        ) from exc

    return {
        "status": "ok",
        "app": settings.app_name,
        "database": "ok",
        "redis": "ok",
        "llm": "not_checked_at_boot",
    }


async def _ping_redis(redis_url: str) -> None:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(b"*1\r\n$4\r\nPING\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.readline(), timeout=2.0)
        if not response.startswith(b"+PONG"):
            raise RuntimeError("unexpected Redis PING response")
    finally:
        writer.close()
        await writer.wait_closed()


# Serve frontend static files
if FRONTEND_DIR:
    # Mount static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static-assets")

    # Serve other static files at root (favicon, icons)
    @app.get("/favicon.svg")
    async def favicon():
        return FileResponse(FRONTEND_DIR / "favicon.svg")

    @app.get("/icons.svg")
    async def icons():
        return FileResponse(FRONTEND_DIR / "icons.svg")

    # SPA catch-all: serve index.html for all non-API routes
    @app.get("/{path:path}")
    async def spa_catch_all(request: Request, path: str):
        # Don't catch API or health routes
        if (
            path.startswith("api/")
            or path == "health"
            or path.startswith("docs")
            or path.startswith("openapi")
        ):
            return None
        return FileResponse(FRONTEND_DIR / "index.html")
