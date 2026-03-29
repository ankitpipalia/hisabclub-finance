#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="8356"
LLM_PORT="8472"

echo "== Docker services =="
cd /home/ankit/Documents/personal-finance-app
docker compose ps

echo
echo "== Backend health =="
curl -fsS "http://localhost:${BACKEND_PORT}/health"

echo
echo "== Backend-served web root =="
curl -fsS "http://localhost:${BACKEND_PORT}/" | head -c 300

echo
echo "== Shared LLM health =="
curl -fsS "http://localhost:${LLM_PORT}/health"

echo
echo "== Shared LLM models =="
curl -fsS "http://localhost:${LLM_PORT}/v1/models"
