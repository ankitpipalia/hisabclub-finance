#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="8356"
LLM_ROOT="/home/ankit/Documents/local-llm"
SHARED_LLM_ENV="$LLM_ROOT/shared-local-llm.env"
ENV_FILE="/home/ankit/Documents/personal-finance-app/.env"

echo "== Docker services =="
cd /home/ankit/Documents/personal-finance-app
docker compose ps

if [[ -f "$SHARED_LLM_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SHARED_LLM_ENV"
  set +a
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

LLM_BASE_URL="${LLM_BASE_URL:-${LOCAL_LLM_QWEN_HOST_API_BASE:-${LOCAL_LLM_TEXT_HOST_API_BASE:-http://127.0.0.1:8097/v1}}}"
LLM_HEALTH_URL="${LLM_BASE_URL%/v1}/health"
LLM_MODELS_URL="${LLM_BASE_URL}/models"

echo
echo "== Backend health =="
curl -fsS "http://localhost:${BACKEND_PORT}/health"

echo
echo "== Backend-served web root =="
curl -fsS "http://localhost:${BACKEND_PORT}/" | head -c 300

echo
echo "== Shared LLM health =="
curl -fsS "$LLM_HEALTH_URL"

echo
echo "== Shared LLM models =="
curl -fsS "$LLM_MODELS_URL"
