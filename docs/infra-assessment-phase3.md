# Infra Assessment - Phase 3
Date: 2026-04-27

Raw local diagnostics were captured in `/tmp/infra_phase3_diagnostics.txt`. Real document inventory/probe outputs are in `/tmp/fy2425_inventory.txt`, `/tmp/fy2425_probe_report.json`, and `/tmp/fy2425_probe_output.txt`.

## Components Assessed

### Job Queue: Kept As-Is
Reason: No observed failure mode justified an ARQ redesign in this phase. The embedded worker claimed and completed real parse jobs sequentially, Redis state keys were written, and no event-loop outage was observed during upload/status polling.

Change: None. ARQ remains a future option if concurrent uploads block the API, job crashes leave unrecoverable partial canonical rows, or per-user queue isolation starts failing under load.

### LLM Routing: Kept As-Is
VRAM budget: NVIDIA RTX A5000 24564 MiB total; Qwen3.6 runtime observed at roughly 23171 MiB used with 939 MiB free during Phase 3.

Reason: The real folder probe found 0 image-only PDFs, so enabling OCR/vision now would add GPU time-sharing complexity without immediate value. Text extraction and template/LLM fallback covered the tested statement files.

Change: None. OCR/vision stays disabled. If scanned PDFs appear later, route them through a separate vision-required job lock rather than loading vision alongside Qwen3.6.

### DB Connection Pool: Kept As-Is
Peak connections observed: 3 active connections during real import checks.

Reason: This is far below the redesign threshold of 15. Existing SQLAlchemy pool settings are sufficient for the current embedded-worker topology.

Change: None.

### Redis Key Hygiene: OK
Keys found: 3 `parserjob:*` keys after real imports.

TTL status: Keys have expirations. Redis keyspace reported `expires=3` with average TTL around 23.9 hours. Code path `backend/app/engines/jobs/parser_state.py` writes parser state with `SET ... EX 86400`.

Change: None.

### SMS/Manual/Split Audit Defaults: Patched
Paths found without extraction audit defaults:

- `backend/app/engines/ledger/merger.py` for SMS/review/manual promotion into canonical transactions.
- `backend/app/api/v1/transactions.py` for split child transactions.

Change: Added minimum audit defaults for non-PDF paths: `extraction_source`, `extraction_confidence`, `source_statement_id` where available, `source_evidence`, `validation_status`, and split lineage.

### Parser Template Coverage: Stubbed
Real probe showed statement-like PDFs from banks without dedicated parsers. Existing full templates remain HDFC/SBI/Axis. Added metadata-only stubs so these banks route deterministically and then fall back to local LLM extraction:

- `BOB` savings
- `ICICI` savings
- `KOTAK` savings
- `KOTAK` credit card

File: `backend/app/engines/parser/templates/generic_bank_stubs.py`

### Logging Hygiene: Patched
Problem observed: parser warnings logged the first 500 characters of statement text, which can include PII.

Change: replaced text previews with a redacted diagnostic token containing char count, line count, and digest only.

### Dedup: Patched After Real Failure
Observed failure: forced re-import of the same BOB statement promoted 1 new row because local LLM extraction flipped direction for one otherwise identical row. The normal dedup key includes direction, which is correct globally but too strict for exact file re-imports.

Change: added an exact-reimport fallback in `backend/app/extraction/promoter.py`. It only activates when an existing statement shares the same source PDF hash or statement fingerprint, then uses a direction/account-insensitive row signature to skip LLM variation duplicates. Normal global dedup remains direction-aware.

### Frontend Chunking: Patched
Before: main frontend JS chunk was 1213.22 kB and Vite warned.

After: route-level lazy loading reduced the main JS chunk to 231.08 kB. Statement PDF viewer is isolated in its own route chunk. The PDF.js worker remains a separate 1046.21 kB worker asset, loaded only by the statement review route.

File: `frontend/src/App.tsx`

## Deferred Decisions

### ARQ Worker
Deferred because no queue corruption or API-blocking failure was observed. Revisit when simultaneous uploads are tested or when parser job duration/concurrency becomes a product bottleneck.

### LLM Time-Share Router
Deferred because OCR backlog is zero and only the text LLM is needed now. Revisit only when scanned PDFs enter the active workload.

### `parse_statement()` Split
Deferred. The function is still monolithic, but no mid-job crash was observed in Phase 3. Splitting it should be done when a real crash/resume failure appears, not preemptively.
