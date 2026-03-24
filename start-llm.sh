#!/bin/bash
# Start llama.cpp server with QwQ-32B model
# Usage: ./start-llm.sh

MODEL_PATH="./models/qwq-32b-q4_k_m.gguf"

if [ ! -f "$MODEL_PATH" ]; then
    echo "Model not found at $MODEL_PATH"
    echo "Download it first or wait for current download to complete"
    exit 1
fi

echo "Starting llama.cpp server with QwQ-32B..."
docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d llm
echo "LLM server starting on http://localhost:8080"
echo "To enable in HisabClub, set LLM_ENABLED=true in .env and restart backend"
