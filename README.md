# HisabClub

HisabClub is a privacy-first, self-hosted Indian personal finance ledger.

## Core capabilities
- imports bank and credit card statements, including password-protected PDFs
- supports local document-folder intake and manual uploads
- builds customer-scoped local document knowledge from prior PDFs to improve later parsing
- uses prompt-versioned iterative LLM extraction (chunked long statements + few-shot examples)
- stitches cross-page PDF tables before LLM fallback to reduce dropped/duplicated rows
- supports tier-2 extraction (deterministic table rows + LLM column mapping) before full JSON fallback
- merges parsed transactions into a unified ledger with transfer reconciliation
- enforces semantic statement dedup in addition to file-hash dedup
- tracks matched debit/credit transfer legs in a dedicated `transfer_matches` table
- applies confidence-gated partial promotion (low-confidence rows are quarantined for review)
- provides budgets, bills, monthly insights, tax-compliance views, and statement PDF viewing
- lets users delete statements and remove their local LLM memory, or re-review a stored statement with the local LLM
- includes local password reset and authenticated password change flows
- keeps document analysis local with an optional shared host LLM
- supports model routing hooks (`small`/`default`/`large`) without changing business logic
- uses durable PostgreSQL-backed extraction jobs with retry and DLQ requeue support
- includes per-user fair queue selection for statement parsing jobs
- enforces multi-gate auto-promotion checks (quarantine, yield-rate, optional CC integrity gate)

## Supported local topology
- backend on host: `http://localhost:8356`
- built web frontend served by the backend at `/`
- PostgreSQL and Redis in Docker
- shared llama.cpp server on host: `http://localhost:8472/v1`
- Expo/Metro for mobile debug on `http://localhost:8081`

## Permanent dev domains
- API default: `https://hisabclub-dev-api.ankit-tech.store/api/v1`
- Web default: `https://hisabclub-dev-web.ankit-tech.store`
- Mobile now defaults to the API domain above and keeps custom self-hosted server entry behind a 3-dot menu.
- Recommended tunnel targets:
  - `hisabclub-dev-api.ankit-tech.store` -> `http://192.168.1.69:8356`
  - `hisabclub-dev-web.ankit-tech.store` -> `http://192.168.1.69:8356`
  - Do not point the public web domain at Vite `:5276`; that port is for optional local-only UI development.

## Quick start
```bash
make setup
make local-stack
```

`make local-stack` starts Postgres and Redis, starts the shared local LLM if needed, builds the frontend, applies migrations, seeds categories and merchants, and runs the backend on the host. The backend then serves both the API and the built web app on `:8356`.

Backfill local document knowledge from existing PDFs:
```bash
make backfill-knowledge
```

Validate the running stack:
```bash
make local-check
```

## Shared local LLM
The repo no longer owns its own LLM runtime. It expects the shared stack under `/home/ankit/Documents/local-llm`.

Model path:
- `/home/ankit/Documents/local-llm/models/unsloth-Qwen3.5-27B-GGUF/Qwen3.5-27B-Q3_K_M.gguf`

Manual start:
```bash
cd /home/ankit/Documents/local-llm
./llama-turbo-cuda.sh start
```

The backend now stores local document chunks in PostgreSQL and retrieves same-user context during statement classification and fallback parsing. This is local retrieval, not a hosted vector service.
Prompt templates and versions are in `backend/app/engines/llm/prompts.py`.

## Mobile debug
```bash
make android-install
make mobile-dev
```

If a physical device is attached over USB, `make mobile-dev` applies `adb reverse` for `8356` and `8081` before starting Metro.

## Web development
- Stable/public path: use backend-served web on `http://localhost:8356`
- Optional hot-reload UI dev: `cd frontend && npm run dev` on `http://localhost:5276`
- Public tunnels should target `:8356`, not `:5276`

## Account recovery
- `POST /api/v1/auth/forgot-password` issues a one-time reset token.
- In local mode without SMTP, the API returns a `preview_url` so the reset flow can be exercised without email delivery.
- The web app exposes `/reset-password`, and authenticated users can rotate credentials from the web Account page or the mobile Settings screen.

## Upload pipeline and ops APIs
- `POST /api/v1/upload/pdf` now enqueues parsing and immediately returns `status=reviewing`.
- `GET /api/v1/upload/{pdf_id}/status` reports queue/statement state (reviewing, success, review_required, error, failed, duplicate).
- `GET /api/v1/upload/jobs/dlq` lists dead-letter parse jobs for the signed-in user.
- `POST /api/v1/upload/jobs/{job_id}/requeue` retries a DLQ job after fixing password/parser issues.
- `GET /api/v1/upload/parser-health` shows per-bank parser success/failure plus yield-rate counters.

## Local architecture POC scripts
Run with backend virtualenv:
```bash
backend/.venv/bin/python scripts/poc_table_stitch_eval.py --limit 20
backend/.venv/bin/python scripts/poc_llm_column_mapping_eval.py --limit 10
backend/.venv/bin/python scripts/poc_ocr_compare.py --limit 20
```

## Review and reconciliation APIs
- `GET /api/v1/reviews/tasks` lists open/resolved statement review tasks.
- `POST /api/v1/reviews/tasks/{task_id}/resolve` resolves low-confidence quarantine with `promote` or `ignore`.
- `POST /api/v1/transactions/reconcile-upi-failures` auto-links failed UPI debits with reversal credits.
- `POST /api/v1/transactions/reclassify-transfer-payments` still handles card-payment transfer matching.

## Gmail encrypted PDFs
- Gmail sync now enqueues parse jobs (it no longer parses attachments inline).
- Add password patterns per bank via:
  - `GET /api/v1/gmail/password-patterns`
  - `PUT /api/v1/gmail/password-patterns`
  - `DELETE /api/v1/gmail/password-patterns/{pattern_id}`
- Pattern templates support variables from `variables` (for example `"{customer_id}{dob_ddmmyyyy}"`).
- Credentials remain encrypted at rest (`DATA_ENCRYPTION_KEY`).

## Tenant isolation hardening
- RLS policies are enabled on user-scoped tables and enforced through request context:
  - app sets `app.current_user_id` on authenticated requests
  - worker loops set `app.worker_mode=1`
- Runtime sessions switch to `hisabclub_rls` (`SET ROLE`) by default, so RLS is enforced even if the connection user is bootstrap/admin.
- Config knobs: `DB_SET_ROLE_ON_CONNECT=true`, `DB_RLS_ROLE=hisabclub_rls`.

## Storage tiering
- Parsed statements can be moved from hot upload paths to cold archive storage automatically.
- Config knobs:
  - `COLD_STORAGE_ENABLED=true`
  - `COLD_STORAGE_DIR=./uploads/cold`

## Verification
- backend health: `curl http://localhost:8356/health`
- recent review feed: `GET /api/v1/upload/recent`
- backend tests: `cd backend && .venv/bin/pytest -q`
- frontend build: `cd frontend && npm run build`
- mobile typecheck: `cd mobile && npx tsc --noEmit`

## Current caveats
- Gmail OAuth requires valid `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`.
- Gmail OAuth credentials are now encrypted at rest; set `DATA_ENCRYPTION_KEY` in production.
- Parser coverage is still strongest for HDFC, Axis, and SBI statement formats.
- The web production build currently emits a Vite large-chunk warning, but the app builds and runs correctly.

## Knowledge transfer
See `knowledge.md` for complete architecture, migrations, model paths, and rollout history.
