.PHONY: dev dev-backend dev-frontend migrate seed backfill-knowledge test lint docker-up docker-down \
	local-services local-stack local-check android-install android-reverse mobile-dev

VENV = .venv/bin

# Development
dev:
	@echo "Starting HisabClub with backend-served web on :8356..."
	./scripts/start-local-stack.sh

dev-backend:
	cd backend && $(VENV)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8356

dev-frontend:
	cd frontend && npm run dev

# Database
migrate:
	cd backend && $(VENV)/alembic upgrade head

migrate-new:
	cd backend && $(VENV)/alembic revision --autogenerate -m "$(msg)"

seed:
	cd backend && $(VENV)/python -m app.seed.run

backfill-knowledge:
	cd backend && $(VENV)/python -m app.tasks.backfill_document_knowledge

# Testing
test:
	cd backend && $(VENV)/pytest -v

test-cov:
	cd backend && $(VENV)/pytest --cov=app --cov-report=html

# Linting
lint:
	cd backend && $(VENV)/ruff check app/ tests/
	cd backend && $(VENV)/ruff format --check app/ tests/

format:
	cd backend && $(VENV)/ruff check --fix app/ tests/
	cd backend && $(VENV)/ruff format app/ tests/

# Docker
docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-build:
	docker compose build

# Supported local topology: db/redis in Docker, backend on host, shared LLM in /home/ankit/Documents/local-llm
local-services:
	docker compose up -d db redis

local-stack:
	./scripts/start-local-stack.sh

local-check:
	./scripts/check-local-stack.sh

android-install:
	./scripts/install-mobile-debug.sh

android-reverse:
	./scripts/android-reverse.sh

mobile-dev:
	./scripts/start-mobile-dev.sh

# Setup
setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install
	cp -n .env.example .env || true
	mkdir -p uploads
	@echo "Setup complete. Use 'make local-stack' for the supported host-backend workflow."
