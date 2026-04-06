# HisabClub Extraction Pipeline: Runtime-Aligned Plan and Implementation Record

## 1. Purpose

This document is now the active implementation plan for the statement/document AI pipeline.
It replaces the stale assumption that the system is still centered on a fixed `Qwen3.5-27B + GLM-OCR` pair.

It does three jobs:
- records the current local LLM runtime truth from `/home/ankit/Documents/local-llm/README.md`
- records what is already implemented in the backend
- defines the next-phase architecture for optional vision-first extraction using a dedicated model such as `Qwen3-VL-8B-Instruct`

Date: `2026-04-06`

---

## 2. Runtime Truth

### Local LLM runtime outside this repo

The current shared serving stack under `/home/ankit/Documents/local-llm` is:
- TurboQuant-enabled `llama.cpp`
- OpenAI-compatible `/v1`
- primary application endpoint serving on `0.0.0.0:8096`
- primary hosted model: `Qwen3-VL-8B-Instruct-Q4_K_M.gguf`
- OCR endpoint serving separately on `0.0.0.0:8095`

### Current application reality

The repo now runs with `Qwen3-VL-8B` as the active application model route. Historical references to `:8472` remain only as legacy documentation and should not drive current backend behavior.

### Architectural consequence

The application must treat local LLM access as routed infrastructure, not as a single fixed endpoint.

That is now implemented through:
- routed text client construction
- separate OCR endpoint support
- optional dedicated vision extraction endpoint support
- primary PDF-page-image extraction support when a vision model is explicitly enabled

### Storage decision

PostgreSQL remains the system of record.

Reason:
- canonical ledger promotion is transactional
- dedup + review + audit trails are relational
- statement/version lineage is relational
- replacing it with NoSQL would reduce correctness and increase implementation risk without helping `PDF -> JSON` extraction

---

## 3. Model Topology Going Forward

### Current supported topology

| Workload | Endpoint type | Default state | Notes |
|---|---|---|---|
| text extraction / classification / review | shared text LLM | active | current app-compatible path |
| OCR page transcription | optional vision/OCR endpoint | optional | page-selective fallback |
| vision-first statement extraction | optional dedicated vision endpoint | newly supported in code | intended for models such as `Qwen3-VL-8B` |

### Recommended target topology

| Workload | Recommended model | Why |
|---|---|---|
| statement page image extraction | `Qwen3-VL-8B-Instruct (GGUF)` | best fit for Indian statement/table extraction from rendered PDF pages |
| text-only fallback / metadata / review | `Qwen3.5-27B` or current shared text model | strong structured JSON behavior |
| OCR-style plain transcription | existing OCR endpoint or separate lightweight vision model | cheaper than full vision extraction when only text recovery is needed |

### Important constraint

The current TurboQuant launcher and existing llama.cpp runtime must not be broken or silently reconfigured by backend code. The backend must adapt by configuration only.

---

## 4. Architecture Delta Implemented

### 4.1 Routed LLM client layer

New module:
- `backend/app/engines/llm/factory.py`

Implemented:
- `build_client_for_task(...)`
- `resolve_target_for_task(...)`
- `build_ocr_client()`
- `should_use_vision_for_statement_extraction(...)`

This removes direct `LLMClient(base_url=..., model=...)` construction from multiple backend workflows and replaces it with a task-based routing layer.

### 4.2 New config surface

Updated:
- `backend/app/config.py`
- `.env.example`

Added:
- `LLM_RUNTIME_LABEL`
- `LLM_VISION_ENABLED`
- `LLM_VISION_BASE_URL`
- `LLM_VISION_API_KEY`
- `LLM_VISION_MODEL`
- `LLM_VISION_STATEMENT_EXTRACTION_ENABLED`
- `LLM_VISION_RENDER_DPI`
- `LLM_VISION_PAGE_LIMIT`

This allows the app to keep working on the existing text endpoint while adding a separate dedicated vision model later.

### 4.3 Vision JSON support

Updated:
- `backend/app/engines/llm/client.py`

Added:
- `chat_vision_json(...)`

This makes multimodal page-image extraction compatible with the same structured JSON contract used elsewhere in the backend.

### 4.4 Vision-first statement extraction path

New module:
- `backend/app/engines/llm/vision_statement.py`

Implemented behavior:
- render PDF pages locally
- send page images to a vision-capable OpenAI-compatible endpoint
- request strict JSON page extraction
- merge transactions deterministically
- preserve metadata when available
- dedupe rows by date + amount + direction + description prefix

This is not yet the only extraction path. It is an optional routed path that can be enabled without rewriting the parser layer.

### 4.5 Parser orchestration changes

Updated:
- `backend/app/engines/parser/base.py`

Implemented:
- OCR client creation now uses the routed factory
- text extraction/classification clients now use the routed factory
- no-parser and zero-transaction fallback paths can optionally try the vision extractor before the text-only iterative fallback

### 4.6 Other AI call sites migrated

Updated:
- `backend/app/api/v1/upload.py`
- `backend/app/engines/insights/statement_integrity.py`
- `backend/app/engines/ledger/transfer_reclassifier.py`
- `backend/app/engines/llm/correction_chat.py`
- `backend/app/engines/llm/router.py`

Effect:
- document auto-classification
- integrity review
- transfer reclassification
- correction chat
all now consume the routed client layer instead of constructing raw LLM clients inline.

---

## 5. What Was Already Implemented Before This Update

The following remained valid and are not being re-proposed:
- selective OCR fallback for low-signal pages
- deterministic statement validation before promotion
- bank-account balance-walk checks
- structured JSON cleanup and parse hardening
- account-aware dedup improvements
- transfer/card-payment classification fixes
- statement integrity review hardening
- spreadsheet-aware artifact ingestion for tax/demat documents

That work remains part of the active architecture.

---

## 6. Extraction Flow After This Update

```text
Upload PDF
  -> decrypt
  -> native text extraction
  -> low-signal assessment
      -> optional OCR page transcription
  -> parser detection
      -> template parser if supported
      -> if parser missing or template returns zero transactions:
           optional vision-first page extraction
           fallback to text-only iterative LLM extraction
  -> deterministic validation
  -> semantic dedup / promotion gating
  -> integrity and review workflows
```

### Key design rule

Vision extraction is additive, not a blind replacement.
The system still prefers deterministic parser output when template support exists.

---

## 7. Qwen3-VL Recommendation Integration

### Recommendation accepted into architecture

`Qwen3-VL-8B-Instruct (GGUF)` is now both:
- the recommended dedicated model for `vision-first statement extraction`
- the current active local model route for the application

### Why this fits the product

- strong table/document understanding for Indian bank and card statement layouts
- strict JSON extraction capability
- runs locally on the available RTX A5000 class hardware
- avoids shipping sensitive statement data to external providers
- better direct page-image understanding than text-only LLM + OCR-only flows on messy scans

### How this is represented in code now

The repo is now configured to use `Qwen3-VL-8B` directly:
- `LLM_BASE_URL=http://localhost:8096/v1`
- `LLM_MODEL=Qwen3-VL-8B-Instruct-Q4_K_M.gguf`
- `LLM_VISION_ENABLED=true`
- `LLM_VISION_BASE_URL=http://localhost:8096/v1`
- `LLM_VISION_MODEL=Qwen3-VL-8B-Instruct-Q4_K_M.gguf`
- `LLM_VISION_STATEMENT_EXTRACTION_ENABLED=true`
- `LLM_VISION_STATEMENT_PRIMARY=true`

This keeps the backend provider-agnostic while making Qwen3-VL the real production path.

### Additional runtime work completed

- folder imports now commit per file instead of holding the whole directory in one transaction
- tenant RLS context is re-applied after incremental commits
- statement-path knowledge ingestion now commits before the heavy parse begins
- real-data validation against `/home/ankit/Documents/FY24-25-Ankit-details` has already parsed:
  - BOB savings statement (`13` rows)
  - HDFC credit card statement (`66` rows)
  - ICICI savings statement (`186` rows)

---

## 8. Current Code Map

### Config and routing
- `backend/app/config.py`
- `backend/app/engines/llm/factory.py`
- `backend/app/engines/llm/router.py`
- `.env.example`

### Client and vision extraction
- `backend/app/engines/llm/client.py`
- `backend/app/engines/llm/vision_statement.py`

### Parser and OCR integration
- `backend/app/engines/parser/base.py`
- `backend/app/engines/parser/ocr.py`
- `backend/app/engines/parser/validation.py`

### Other routed AI workflows
- `backend/app/api/v1/upload.py`
- `backend/app/engines/insights/statement_integrity.py`
- `backend/app/engines/ledger/transfer_reclassifier.py`
- `backend/app/engines/llm/correction_chat.py`

### Tests added for this phase
- `backend/tests/test_llm/test_client.py`
- `backend/tests/test_llm/test_factory.py`
- `backend/tests/test_llm/test_vision_statement.py`
- `backend/tests/test_parser/test_ocr_validation.py`

---

## 9. Status By Phase

### Phase A — correctness fixes
Status: `implemented`

### Phase B — selective OCR fallback
Status: `implemented`

### Phase C — routed model/client abstraction
Status: `implemented`

### Phase D — optional vision-first extraction path
Status: `implemented in backend code`

Behavior:
- if `LLM_VISION_ENABLED=true`
- and `LLM_VISION_STATEMENT_EXTRACTION_ENABLED=true`
- and `LLM_VISION_STATEMENT_PRIMARY=true`

then page-image extraction is attempted before template parsing and text-only fallback.

### Phase E — dedicated Qwen3-VL deployment and benchmark
Status: `pending operational rollout`

---

## 10. Remaining Work

### High priority
- deploy a dedicated local vision endpoint for `Qwen3-VL-8B`
- benchmark primary vision extraction on real Indian statements vs current text/OCR path
- decide whether scanned-document fallback should use:
  - OCR transcription first
  - direct vision extraction first
  - hybrid by text-quality score

### Medium priority
- add statement-source observability for routed model choice
- expose `text route / OCR route / vision route` in review/admin diagnostics
- add end-to-end tests for routed vision extraction in real parser jobs

### Low priority
- promote routed client creation into any remaining non-critical AI helpers
- add benchmark notes back into `knowledge.md` and `ARCHITECTURE.md` after operational deployment

---

## 11. Verification Completed For This Update

Verified in backend:
- routed client factory compiles and passes tests
- OCR path still compiles
- parser orchestration compiles after routing change
- optional vision extraction path has regression coverage
- updated tests passed:
  - `tests/test_llm/test_client.py`
  - `tests/test_llm/test_factory.py`
  - `tests/test_llm/test_vision_statement.py`
  - `tests/test_parser/test_ocr_validation.py`

---

## 12. Practical Enablement Example

Example env for future dedicated vision rollout:

```env
LLM_ENABLED=true
LLM_BASE_URL=http://127.0.0.1:8094/v1
LLM_MODEL=Qwen3.5-27B-Q3_K_M.gguf

LLM_VISION_ENABLED=true
LLM_VISION_BASE_URL=http://127.0.0.1:8096/v1
LLM_VISION_MODEL=Qwen3-VL-8B-Q4_K_M.gguf
LLM_VISION_STATEMENT_EXTRACTION_ENABLED=true
```

With that setup:
- standard classification/review stays on the text model
- image-heavy fallback extraction can shift to the vision model
- no business-logic rewrite is required

---

## 13. Final Position

The correct architecture for this product is now:
- deterministic finance pipeline first
- local routed model abstraction second
- optional dedicated vision extraction model for hard PDFs
- no hard dependency on one fixed llama.cpp endpoint or one fixed model

That is the path now implemented in code.
