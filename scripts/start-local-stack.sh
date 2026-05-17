#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ankit/Documents/personal-finance-app"
LLM_ROOT="/home/ankit/Documents/local-llm"
SHARED_LLM_ENV="$LLM_ROOT/shared-local-llm.env"
SHARED_LLM_SCRIPT="$LLM_ROOT/shared-local-llm.sh"
BACKEND_PORT="8356"
ENV_FILE="$ROOT/.env"
LEGACY_LLM_BASE_URLS=(
  "http://localhost:8472/v1"
  "http://127.0.0.1:8472/v1"
  "http://localhost:8096/v1"
  "http://127.0.0.1:8096/v1"
)
LEGACY_LLM_MODELS=(
  "Qwen3.5-27B-Q3_K_M.gguf"
  "Qwen3-VL-8B-Instruct-Q4_K_M.gguf"
)

cd "$ROOT"

if ! command -v npm >/dev/null 2>&1; then
  NVM_NODE_BIN="$(find /home/ankit/.nvm/versions/node -maxdepth 3 -name npm -printf '%h\n' 2>/dev/null | sort -V | tail -n 1)"
  if [[ -n "${NVM_NODE_BIN:-}" ]]; then
    export PATH="$NVM_NODE_BIN:$PATH"
  fi
fi

if [[ ! -f "$SHARED_LLM_ENV" || ! -x "$SHARED_LLM_SCRIPT" ]]; then
  echo "Shared local LLM contract is missing. Expected:" >&2
  echo "  env: $SHARED_LLM_ENV" >&2
  echo "  script: $SHARED_LLM_SCRIPT" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$SHARED_LLM_ENV"
set +a

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PRIMARY_LLM_BASE_URL="${LOCAL_LLM_QWEN_HOST_API_BASE:-${LOCAL_LLM_TEXT_HOST_API_BASE}}"
PRIMARY_LLM_MODEL="${LOCAL_LLM_QWEN_MODEL:-${LOCAL_LLM_TEXT_MODEL}}"

export LLM_BASE_URL="${LLM_BASE_URL:-$PRIMARY_LLM_BASE_URL}"
for legacy_url in "${LEGACY_LLM_BASE_URLS[@]}"; do
  if [[ "$LLM_BASE_URL" == "$legacy_url" ]]; then
    export LLM_BASE_URL="$PRIMARY_LLM_BASE_URL"
    break
  fi
done

export LLM_MODEL="${LLM_MODEL:-$PRIMARY_LLM_MODEL}"
for legacy_model in "${LEGACY_LLM_MODELS[@]}"; do
  if [[ "$LLM_MODEL" == "$legacy_model" ]]; then
    export LLM_MODEL="$PRIMARY_LLM_MODEL"
    break
  fi
done

export LLM_VISION_BASE_URL="${LLM_VISION_BASE_URL:-$LOCAL_LLM_VISION_HOST_API_BASE}"
export LLM_VISION_MODEL="${LLM_VISION_MODEL:-$LOCAL_LLM_VISION_MODEL}"
export LLM_STARTUP_VALIDATION="${LLM_STARTUP_VALIDATION:-false}"
export LLM_REQUIRED_FOR_BOOT="${LLM_REQUIRED_FOR_BOOT:-false}"

docker compose up -d db redis
docker compose stop api >/dev/null 2>&1 || true

LLM_HEALTH_URL="${LLM_BASE_URL%/v1}/health"
LLM_HOST_PORT="${LLM_BASE_URL#http://}"
LLM_HOST_PORT="${LLM_HOST_PORT#https://}"
LLM_HOST_PORT="${LLM_HOST_PORT%%/*}"

if [[ "$LLM_STARTUP_VALIDATION" == "true" ]] && ! curl -fsS "$LLM_HEALTH_URL" >/dev/null 2>&1; then
  if [[ "$LLM_BASE_URL" == "${LOCAL_LLM_QWEN_HOST_API_BASE:-}" ]]; then
    echo "Starting shared local Qwen text LLM via $SHARED_LLM_SCRIPT"
    bash "$SHARED_LLM_SCRIPT" start qwen
    for _ in $(seq 1 30); do
      if curl -fsS "$LLM_HEALTH_URL" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  elif [[ "$LLM_BASE_URL" == "${LOCAL_LLM_TEXT_HOST_API_BASE:-}" ]]; then
    echo "Starting shared local text LLM via $SHARED_LLM_SCRIPT"
    bash "$SHARED_LLM_SCRIPT" start text
    for _ in $(seq 1 30); do
      if curl -fsS "$LLM_HEALTH_URL" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi

  if ! curl -fsS "$LLM_HEALTH_URL" >/dev/null 2>&1; then
    echo "Configured LLM endpoint is not healthy: $LLM_HEALTH_URL" >&2
    if [[ "$LLM_REQUIRED_FOR_BOOT" == "true" ]]; then
      exit 1
    fi
    echo "Continuing because LLM_REQUIRED_FOR_BOOT=false"
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
