#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ankit/Documents/personal-finance-app"
LLM_ROOT="/home/ankit/Documents/local-llm"
BACKEND_PORT="8356"
ENV_FILE="$ROOT/.env"
DEFAULT_LLM_PORT="8472"
DEFAULT_LLM_MODEL_PATH="$LLM_ROOT/models/unsloth-Qwen3.5-27B-GGUF/Qwen3.5-27B-Q3_K_M.gguf"

cd "$ROOT"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

docker compose up -d db redis
docker compose stop api >/dev/null 2>&1 || true

LLM_HEALTH_URL="${LLM_BASE_URL%/v1}/health"
LLM_HOST_PORT="${LLM_BASE_URL#http://}"
LLM_HOST_PORT="${LLM_HOST_PORT#https://}"
LLM_HOST_PORT="${LLM_HOST_PORT%%/*}"
LLM_PORT="${LLM_HOST_PORT##*:}"
LLM_MODEL_PATH="${LLM_LOCAL_MODEL_PATH:-$DEFAULT_LLM_MODEL_PATH}"

if ! curl -fsS "$LLM_HEALTH_URL" >/dev/null 2>&1; then
  if [[ "$LLM_HOST_PORT" == "localhost:${DEFAULT_LLM_PORT}" || "$LLM_HOST_PORT" == "127.0.0.1:${DEFAULT_LLM_PORT}" ]]; then
    echo "Starting shared local LLM on :${LLM_PORT}"
    (cd "$LLM_ROOT" && MODEL="$LLM_MODEL_PATH" PORT="$LLM_PORT" ./llama-turbo-cuda.sh start)
  else
    echo "Configured LLM endpoint is not healthy: $LLM_HEALTH_URL" >&2
    exit 1
  fi
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
