.PHONY: dev dev-backend dev-frontend migrate seed test lint docker-up docker-down

VENV = backend/.venv/bin

# Development
dev:
	@echo "Starting HisabClub in development mode..."
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && $(VENV)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# Database
migrate:
	cd backend && $(VENV)/alembic upgrade head

migrate-new:
	cd backend && $(VENV)/alembic revision --autogenerate -m "$(msg)"

seed:
	cd backend && $(VENV)/python -m app.seed.run

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

# Setup
setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install
	cp -n .env.example .env || true
	mkdir -p uploads
	@echo "Setup complete! Run 'make docker-up' to start PostgreSQL and Redis, then 'make migrate' and 'make dev'"
