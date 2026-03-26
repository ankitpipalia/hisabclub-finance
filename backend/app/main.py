import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.config import settings

# Path to built frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Privacy-first Indian personal finance ledger",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


# Serve frontend static files
if FRONTEND_DIR.exists():
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
        if path.startswith("api/") or path == "health" or path.startswith("docs") or path.startswith("openapi"):
            return None
        return FileResponse(FRONTEND_DIR / "index.html")
