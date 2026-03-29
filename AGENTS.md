# Repository Guidelines

## Project Structure & Module Organization
This repository is a monorepo with three apps:
- `backend/`: FastAPI service. Core code is in `app/` (`api/v1`, `models`, `schemas`, `engines`), migrations in `alembic/`, and tests in `tests/`.
- `frontend/`: Vite + React + TypeScript web app. Main folders are `src/pages`, `src/components`, and `src/api`.
- `mobile/`: Expo React Native app. Main folders are `src/screens`, `src/navigation`, `src/sms`, and `src/api`.
- Root-level infra and runtime files include `docker-compose.yml`, `uploads/`, and `knowledge.md`. Shared LLM assets live outside this repo under `/home/ankit/Documents/local-llm`.

## Build, Test, and Development Commands
- `make setup`: create backend virtualenv, install backend/frontend dependencies, and initialize local files.
- `make docker-up` / `make docker-down`: start/stop Postgres + Redis.
- `make migrate`: apply Alembic migrations.
- `make dev`: run backend (`:8356`) and frontend (`:5276`) together.
- `make test` / `make test-cov`: run backend pytest suite and optional coverage HTML output.
- `make lint` / `make format`: run Ruff checks/formatting for backend.
- `cd frontend && npm run build`: production web build.
- `cd mobile && npm run start` (or `npm run android`): run mobile app.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` for modules/functions, `PascalCase` for classes, max line length 100 (`ruff`).
- TypeScript/TSX: 2-space indentation, semicolons, `PascalCase` component/screen/page files (for example, `DashboardPage.tsx`, `SmsSyncScreen.tsx`), `camelCase` helpers.
- Keep API client code in each app’s `src/api` and avoid mixing backend-only concerns into UI layers.

## Testing Guidelines
- Backend tests use `pytest` with `pytest-asyncio` (`backend/pyproject.toml`).
- Add tests under `backend/tests/test_<area>/test_*.py` (for example, `backend/tests/test_api/test_auth.py`).
- Run `make test` before opening a PR; use `make test-cov` when changing parser/ledger logic.
- Frontend/mobile automated tests are not configured yet; include manual verification notes for UI flows in PRs.

## Commit & Pull Request Guidelines
- Current branch has no commit history yet; use Conventional Commit style going forward (`feat:`, `fix:`, `chore:`, `refactor:`).
- Keep commits scoped and atomic (backend, frontend, or mobile), and include migration files with schema changes.
- PRs should include: concise summary, linked issue (if any), migration/env changes, test evidence, and screenshots for frontend/mobile updates.

## Security & Configuration Tips
- Do not commit `.env` or secrets. Start from `.env.example`.
- Docker local defaults are Postgres `6543` and Redis `6769`; keep `DATABASE_URL*` and `REDIS_URL` aligned.
- LLM support is optional; enable with `LLM_ENABLED=true` and start the shared server with `/home/ankit/Documents/local-llm/llama-turbo-cuda.sh start`.
