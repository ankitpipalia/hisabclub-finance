# HisabClub Extraction Pipeline: Updated Architecture, Implementation Acknowledgement, and Code Map

## 1. Purpose

This document is no longer just a proposal. It now serves as:

- the architecture delta for the extraction-correctness work
- the implementation acknowledgement for what has been shipped
- the code-path map for future continuation

Date of acknowledgement: `2026-04-01`

---

## 2. Original Goal

The original plan targeted two high-risk gaps:

1. scanned/image PDFs were rejected because OCR did not exist
2. multiple correctness bugs allowed low-quality extracted data to move too close to canonical ledger state

The intended architecture was:

`PDF -> native text extraction -> OCR fallback if needed -> parser/LLM extraction -> deterministic validation -> dedup/promotion -> integrity/review gates`

That architecture is now mostly implemented in the backend.

---

## 3. Current Status Summary

### Implemented

- OCR configuration surface in backend settings and `.env.example`
- multimodal vision support in the shared OpenAI-compatible LLM client
- selective OCR fallback for low-signal/scanned PDF pages
- extraction validation before persistence/promotion
- safer LLM JSON cleanup and chunk-level row normalization
- sanitizer fix so UPI/UTR/IMPS/NEFT/RTGS references survive prompt sanitization
- account-aware dedup improvements
- credit-card payment vs merchant-expense classification fixes
- integrity review switched to structured JSON parsing
- merchant normalization performance improvement through in-process cache
- tighter expected-row heuristics
- bounded date parsing fallback
- targeted regression coverage

### Partially Implemented

- OCR runtime operations:
  - launcher script added
  - actual OCR model deployment and health verification still pending
  - current blocker: no OCR model artifacts are present under `/home/ankit/Documents/local-llm/models`
  - no systemd unit created in this repo phase
- validation layer:
  - implemented as a pragmatic validator
  - full flag-by-flag confidence penalty framework from the original proposal is not yet implemented
- tier-2 metadata extraction:
  - row normalization improved
  - separate dedicated metadata-only LLM call for tier-2 was not added

### Deferred

- production OCR benchmarking on weak scans and public-sector bank layouts
- frontend/mobile OCR-specific observability UX
- repo-wide lint cleanup outside the touched modules

---

## 4. Architecture Actually Implemented

### Runtime model topology

| Model / Endpoint | Role | Port | State |
|---|---|---:|---|
| Existing shared Qwen endpoint | extraction, classification, integrity review | `8472` | kept unchanged |
| Planned OCR vision endpoint | scanned/low-signal page OCR | `8095` | config + launcher added |

Important deviation:

- The original draft assumed Qwen on `8094`.
- Actual implementation intentionally kept the existing shared llama.cpp endpoint on `8472` because the current runtime/model configuration was not to be changed.

### Current extraction flow

```text
Upload PDF
  -> decrypt (pikepdf)
  -> native text extraction (pdfplumber)
  -> assess text quality
      -> if low-signal pages exist and OCR is enabled:
           render only those pages
           send to local vision endpoint
           merge OCR text back into page stream
  -> parser detection / LLM classification
  -> template parse or iterative LLM extraction
  -> deterministic validation of extracted rows
  -> persist parsed rows
  -> promote non-quarantined rows to canonical ledger
  -> integrity and review gates
```

### Core design choices

- OCR is **page-selective**, not document-wide by default.
- Validation happens **inside parser orchestration before persistence/promotion**, not as a separate worker module in this phase.
- Merchant optimization uses **TTL caching**, not statement-scoped preload injection.
- Dedup is improved through **account-aware fingerprinting and same-direction matching**.

---

## 5. Actual Code Paths Changed

### OCR and parser orchestration

- [backend/app/engines/parser/base.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/parser/base.py)
- [backend/app/engines/parser/ocr.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/parser/ocr.py)
- [backend/app/engines/parser/validation.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/parser/validation.py)
- [backend/app/engines/parser/pdf_utils.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/parser/pdf_utils.py)
- [backend/app/engines/parser/amount_utils.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/parser/amount_utils.py)

### LLM client and extraction hardening

- [backend/app/engines/llm/client.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/llm/client.py)
- [backend/app/engines/llm/parse_fallback.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/llm/parse_fallback.py)
- [backend/app/engines/llm/prompts.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/llm/prompts.py)
- [backend/app/engines/llm/sanitizer.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/llm/sanitizer.py)

### Ledger correctness

- [backend/app/engines/ledger/dedup.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/ledger/dedup.py)
- [backend/app/engines/ledger/merger.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/ledger/merger.py)
- [backend/app/engines/ledger/nature.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/ledger/nature.py)
- [backend/app/engines/ledger/merchant_normalizer.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/ledger/merchant_normalizer.py)
- [backend/app/engines/insights/statement_integrity.py](/home/ankit/Documents/personal-finance-app/backend/app/engines/insights/statement_integrity.py)

### Config and runtime support

- [backend/app/config.py](/home/ankit/Documents/personal-finance-app/backend/app/config.py)
- [.env.example](/home/ankit/Documents/personal-finance-app/.env.example)
- [backend/pyproject.toml](/home/ankit/Documents/personal-finance-app/backend/pyproject.toml)
- [/home/ankit/Documents/local-llm/llama-glm-ocr.sh](/home/ankit/Documents/local-llm/llama-glm-ocr.sh)

### Regression coverage

- [backend/tests/test_parser/test_ocr_validation.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_parser/test_ocr_validation.py)
- [backend/tests/test_llm/test_sanitizer_refs.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_llm/test_sanitizer_refs.py)
- [backend/tests/test_llm/test_parse_fallback.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_llm/test_parse_fallback.py)
- [backend/tests/test_ledger/test_dedup.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_ledger/test_dedup.py)
- [backend/tests/test_ledger/test_transaction_nature.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_ledger/test_transaction_nature.py)

---

## 6. Bug Status Against the Original Plan

### Critical

| ID | Original issue | Status | Notes |
|---|---|---|---|
| C1 | float-sensitive dedup comparisons | mitigated | account-aware fingerprint path strengthened; raw SQL paise rounding path not introduced |
| C2 | no account isolation in dedup | implemented | same-account preference added to ref/fuzzy matching |
| C3 | no validation before promotion | implemented | validator added before persistence/promotion |
| C4 | no balance-walk for bank accounts | implemented | savings/current statements now record deterministic balance-walk validation and can be forced to review |
| C5 | integrity includes quarantined rows | implemented | quarantined rows excluded |
| C6 | tier-2 metadata empty | partial | separate metadata-only tier not added |
| C7 | sanitizer strips payment refs | implemented | ref-preserving sanitizer added |
| C8 | exact ref ignores direction | implemented | direction now included in ref match |

### High

| ID | Original issue | Status | Notes |
|---|---|---|---|
| H1 | one invalid row drops full chunk | implemented | rows normalized/validated individually |
| H2 | extraction token ceiling too small | implemented | extraction call increased to `4096` |
| H3 | fragile JSON cleanup | implemented | bracket extraction + cleanup hardened |
| H4 | prompts miss negative rules | implemented | prompt strengthened |
| H5 | `CARD PAYMENT` misclassifies merchant spends | implemented | bill-payment logic tightened |
| H6 | tier-2 confidence hardcoded | partial | confidence improved, but not full scoring matrix |
| H7 | merchant normalizer N+1/full scan cost | implemented | TTL cache added |
| H8 | row-estimate heuristics count summaries | implemented | summary/header filtering tightened |

### Medium

| ID | Original issue | Status | Notes |
|---|---|---|---|
| M1 | few-shot examples too simple | implemented | added more realistic Indian finance examples |
| M2 | knowledge retrieval too broad | deferred | not changed in this phase |
| M3 | unbounded `dateutil.parse()` | implemented | bounded by sanity range |
| M4 | integrity review uses free-form `chat()` | implemented | switched to `chat_json()` |

---

## 7. Phase-by-Phase Acknowledgement

### Phase 1: OCR infrastructure

Status: **partially implemented**

Implemented:
- OCR config keys in settings and env example
- multimodal client support
- OCR helper module
- selective OCR integration in parser flow
- local launcher script:
  - [/home/ankit/Documents/local-llm/llama-glm-ocr.sh](/home/ankit/Documents/local-llm/llama-glm-ocr.sh)

Not yet completed:
- actual OCR model deployment/verification on `8095`
- systemd unit creation

### Phase 2: extraction correctness

Status: **implemented with pragmatic scope**

Implemented:
- validation module
- per-row LLM normalization and validation
- safer sanitizer
- stronger prompts
- better JSON cleanup
- deterministic balance-walk validation for savings/current statements

Deviation:
- validator is simpler than the originally proposed multi-flag scoring object

### Phase 3: dedup and post-processing

Status: **implemented with design simplifications**

Implemented:
- account-aware dedup propagation
- stricter internal-transfer inference
- structured integrity review
- merchant pattern cache
- tighter row estimation
- bounded date parsing

Deviation:
- merchant optimization uses a TTL cache instead of a statement-scoped preload API

### Phase 4: regression tests

Status: **implemented**

Actual files:
- [backend/tests/test_parser/test_ocr_validation.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_parser/test_ocr_validation.py)
- [backend/tests/test_llm/test_sanitizer_refs.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_llm/test_sanitizer_refs.py)
- [backend/tests/test_llm/test_parse_fallback.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_llm/test_parse_fallback.py)
- [backend/tests/test_ledger/test_dedup.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_ledger/test_dedup.py)
- [backend/tests/test_ledger/test_transaction_nature.py](/home/ankit/Documents/personal-finance-app/backend/tests/test_ledger/test_transaction_nature.py)

---

## 8. Verification State

Verified on the current backend codebase:

- compile check on changed backend modules: passed
- targeted backend tests: passed
  - `47 passed`

Covered verification areas:

- OCR quality detection
- OCR fallback merge behavior
- sanitizer reference preservation
- iterative LLM parse fallback
- dedup account-context propagation
- transaction nature classification
- statement integrity logic
- upload/classification/status compatibility

---

## 9. What Changed Architecturally

Compared to the earlier blueprint, the important architectural changes are:

1. **OCR is now a first-class backend path**
- not yet fully operationally deployed
- but code and config paths now exist end-to-end

2. **Validation now sits inside parser orchestration**
- extracted rows are cleaned before they become persisted parsed rows
- this reduces bad data entering downstream dedup/promotion logic

3. **Dedup now uses stronger identity**
- account context now matters
- direction now matters for exact-reference matching

4. **LLM prompting is safer for finance extraction**
- operational refs preserved
- malformed rows are dropped individually
- free-form JSON parsing is reduced

5. **Promotion correctness improved without changing external APIs**
- no schema migrations were required in this phase
- no frontend/mobile API contracts changed in this phase

---

## 10. Remaining Work to Reach the Intended Product State

Backend extraction and correctness are materially stronger now, but the product is not “complete” yet in the absolute sense. The main remaining work from this track is:

1. deploy and benchmark the OCR model on `8095`
2. improve retrieval relevance in `knowledge.py`
3. add end-to-end OCR tests with real scanned PDFs once the service is live
4. add frontend/mobile observability for OCR/review states if needed

---

## 11. Superseded Assumptions

The following original assumptions are now superseded:

- Qwen on `8094`
  - superseded by actual configured shared endpoint `8472`
- “OCR not yet supported”
  - superseded by selective OCR fallback implementation in backend
- “no validation before promotion”
  - superseded by parser-integrated validation

---

## 12. Final Acknowledgement

The extraction-correctness architecture in this file is now substantially implemented in backend code. The codebase has moved from “proposal” to “operational partial delivery” with verified regression coverage. OCR deployment is the main outstanding operational dependency from this track; the parser, LLM, dedup, and integrity code paths have already been updated to support it.
