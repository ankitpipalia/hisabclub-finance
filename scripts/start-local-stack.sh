#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ankit/Documents/personal-finance-app"
LLM_ROOT="/home/ankit/Documents/local-llm"
BACKEND_PORT="8356"
LLM_PORT="8472"

cd "$ROOT"

docker compose up -d db redis
docker compose stop api >/dev/null 2>&1 || true

if ! curl -fsS "http://localhost:${LLM_PORT}/health" >/dev/null 2>&1; then
  echo "Starting shared local LLM on :${LLM_PORT}"
  (cd "$LLM_ROOT" && PORT="$LLM_PORT" ./llama-turbo-cuda.sh start)
fi

echo "Building frontend bundle"
npm --prefix frontend run build

echo "Applying database migrations"
(
  cd backend
  .venv/bin/alembic upgrade head
  .venv/bin/python -m app.seed.run
)

echo "Starting host backend on http://localhost:${BACKEND_PORT}"
cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
