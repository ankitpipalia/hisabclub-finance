# HisabClub Architecture — Consolidated Final Analysis

**Source reviews:** Review A (Claude, this conversation), Review B (external agent, 8.7/10), Review C (external agent, 8.5/10)  
**Synthesis date:** 2026-03-30  
**Methodology:** Agreement = high-confidence finding. Disagreement = adjudicated with reasoning. Unique insight = evaluated and included if valid.

---

## 1. Overall Assessment

### Consensus Score: **8.0 / 10**

The three reviews scored 7.5, 8.7, and 8.5. The 7.5 is justified — the higher scores underweight the concurrency, durability, and ledger consistency gaps that would cause real production incidents. Adjusted to 8.0: this is a genuinely strong architecture document that is above what most fintech startups produce, but has several issues that would cause data corruption or loss if shipped as-is.

### Universal Agreement (All 3 Reviews)

These findings appeared in all three reviews and should be treated as **confirmed issues**:

1. **The raw → normalized → canonical separation is excellent.** This is the architecture's strongest decision and should not be changed.
2. **The modular monolith + async workers topology is correct for MVP.** No reviewer recommends microservices at this stage.
3. **Privacy-first local inference is a real differentiator**, not marketing. It's baked into every layer correctly.
4. **Transfer matching is dangerously underspecified.** All three reviews flag this as a top risk for ledger corruption. The current `transfer_group_id` on `canonical_transactions` is insufficient.
5. **LLM chunking at page boundaries will lose or duplicate transactions.** Cross-page table stitching must happen before LLM extraction, not during.
6. **Self-hosted LLM concurrency is not addressed.** A single 24GB GPU running a 32B model serves ~1-2 concurrent requests. Queue backlog during end-of-month bursts is inevitable.
7. **Prompt templates lack few-shot examples.** Zero-shot extraction from messy OCR underperforms significantly.
8. **Canonical promotion must be wrapped in a database transaction.** Partial promotion = orphaned ledger entries.
9. **PDF parsing is a security attack vector** that needs sandboxing beyond what's currently specified.

### Where Reviews Disagree (Adjudicated)

| Topic | Review A | Review B | Review C | Verdict |
|---|---|---|---|---|
| **SHA-256 file dedup** | Valid but incomplete | Valid but incomplete | "Will fail — banks regenerate PDFs with different metadata" | **Review C is correct.** The same statement downloaded twice from net banking produces different hashes due to embedded timestamps. SHA-256 should remain as a fast-path optimization, but Level 2 semantic fingerprinting (institution + account + period + opening balance) must be the authoritative dedup layer. |
| **Single-entry vs double-entry ledger** | Not raised as critical | Not raised as critical | "Must move to double-entry postings model before writing code" | **Review C raises a valid point but overstates urgency.** Double-entry is ideal for a full accounting system, but HisabClub is a personal finance tracker, not an accounting platform. The `transfer_group_id` approach works if enforced with a dedicated `transfer_matches` table and balanced-pair validation. Recommend: build the `transfer_matches` table now (all reviews agree), defer full double-entry to Phase 2 only if transfer complexity proves unmanageable. |
| **OCR stack (Tesseract vs PaddleOCR/DocTR)** | Not raised | "Replace with PaddleOCR/DocTR immediately" | "Tesseract is notoriously slow" | **Reviews B and C are directionally correct.** Tesseract struggles with Indian multi-script documents and table layouts. However, "replace immediately" is premature — the right move is a **POC comparing Tesseract vs PaddleOCR vs DocTR on 30 real Indian bank scans** before committing. If PaddleOCR wins (likely), swap before MVP. |
| **Queue technology (Redis vs Temporal vs PostgreSQL)** | "Use PostgreSQL-backed job state, Redis as notification only" | "Replace with Temporal before Phase 2" | "Consider PostgreSQL-based queue (Graphile Worker)" | **Reviews A and C converge on PostgreSQL-backed job durability, which is correct and simpler.** Temporal is powerful but adds massive operational complexity for MVP. Recommendation: PostgreSQL job table + Redis pub/sub for MVP. Evaluate Temporal only if the extraction saga becomes unmanageably complex in Phase 2. |
| **Worker consolidation** | Separate workers are fine | "Over-engineered for MVP — merge into one document_processor worker" | Separate workers are fine | **Review B has a point for MVP simplicity**, but the separation is cheap (same codebase, different entry points) and prevents GPU-bound LLM work from starving CPU-bound OCR. Keep separate workers but allow running them on the same host with resource limits. |
| **Password handling for Gmail-synced PDFs** | Not specifically addressed | Not specifically addressed | "Implement deterministic password guessing (HDFC = Customer ID, etc.)" | **Review C raises a real gap the others missed.** Gmail-synced PDFs are almost always password-protected, and the architecture has no path for automatic decryption. A password pattern registry per institution is essential for Gmail import to actually work. |

---

## 2. Consolidated Critical Findings

### Tier 1: Will Cause Data Loss or Corruption (Fix Before Any User)

**F1. No job durability guarantee.**  
*Source: Review A (primary), Review C (supporting)*  
Redis-backed queues (Dramatiq/RQ) will lose in-flight jobs on Redis restart, OOM, or misconfigured eviction. For a financial system where every document must reach a terminal state, this is unacceptable.  
**Fix:** PostgreSQL `jobs` table as the source of truth for job state. Redis as notification/dispatch only. Workers poll PostgreSQL if Redis is unavailable.

**F2. Canonical promotion is not atomic.**  
*Source: All three reviews*  
The promotion step creates canonical transactions, transaction_sources, updates statement status, and may create transfer groups. A crash mid-promotion creates orphaned ledger entries and a statement stuck in a non-terminal state.  
**Fix:** Single PostgreSQL transaction wrapping the entire promotion: insert normalized → dedupe check → create canonical → create sources → update statement status. All or nothing.

**F3. No concurrency control for overlapping work.**  
*Source: Review A (primary)*  
What happens when: (a) two workers pick up related jobs for the same statement, (b) a user triggers reprocess while extraction is in-flight, (c) a review is submitted while a background job is modifying the same data?  
**Fix:** Advisory locks or `SELECT ... FOR UPDATE` on statement rows during state transitions. Optimistic locking on review tasks. Extraction jobs must check current statement status before proceeding.

**F4. Statement versioning enforcement is missing.**  
*Source: Review B (primary), Review A (supporting)*  
`statements.version_no` and `supersedes_statement_id` exist in the schema but enforcement is undefined. Reprocessing can create duplicate canonical transactions if the old version isn't explicitly superseded.  
**Fix:** Enforce single active version per statement lineage. Promotion job must soft-delete canonical transactions from the previous version within the same transaction.

### Tier 2: Will Cause Incorrect Data or Poor UX (Fix Before MVP)

**F5. Transaction deduplication fingerprint is undefined.**  
*Source: Review A (primary), Review C (supporting)*  
The most important correctness algorithm in the system is left to implementation. The `reference_fingerprint` on `normalized_transactions` has no specified algorithm.  
**Fix:** Define explicitly: `SHA-256(user_id || account_id || date_iso || abs(amount_paise) || normalize(description)[0:30])`. Test against real statements with known duplicates. Document edge cases (same-day same-amount different merchants).

**F6. SHA-256 file dedup will produce false negatives.**  
*Source: Review C (primary), all reviews acknowledge limitations*  
Indian bank PDFs embed generation timestamps, download metadata, and session tokens. The same statement downloaded twice produces different hashes.  
**Fix:** Keep SHA-256 as a fast-path exact-match check. Add Level 2 semantic fingerprinting: `(user_id, institution_id, masked_account, period_start, period_end, opening_balance)`. This is the authoritative dedup layer.

**F7. Cross-page table stitching must happen before LLM extraction.**  
*Source: All three reviews*  
Indian bank statements frequently break transactions across pages. Sending page-bounded chunks to the LLM will drop or duplicate rows at boundaries.  
**Fix:** Use `pdfplumber`/`camelot` to detect table structures, stitch tables across page breaks programmatically, then chunk by row count (e.g., 50 rows per chunk) with overlap. Mark overlap rows as `context_only: true`.

**F8. Gmail-synced PDFs have no password resolution path.**  
*Source: Review C (primary, unique insight)*  
Bank statements emailed to users are almost always password-protected. The architecture has no mechanism for automatic decryption during background Gmail sync.  
**Fix:** Implement an institution-specific password pattern registry (HDFC = Customer ID, ICICI = DOB pattern, SBI = account number, etc.). User provides their patterns once during account setup. Auto-attempt before falling back to `pdf_password_challenge` state.

**F9. Upload API returns premature `statement_id`.**  
*Source: Review A (primary)*  
The upload response includes `statement_id` before classification runs. This creates a shell entity that may never be valid.  
**Fix:** Return only `document_id` at upload. Statement is created by the classification worker. Client polls document status.

**F10. No tenant isolation enforcement at the database level.**  
*Source: Review A (primary), Review C (supporting)*  
Multi-tenant isolation depends entirely on every query including `WHERE user_id = :current_user`. One missed filter = financial data leak.  
**Fix:** Implement PostgreSQL Row Level Security (RLS) on all user-scoped tables. Set `current_user_id` session variable per request.

### Tier 3: Will Cause Operational Pain (Fix Before Production Scale)

**F11. Transfer matching needs a dedicated data model.**  
*Source: All three reviews*  
Transfer matching (savings→card payment, UPI self-transfer, NEFT to own account) cannot live as a `transfer_group_id` column. It needs a dedicated table tracking match confidence, matched statement pairs, and resolution status.  
**Fix:** Create `transfer_matches` table: `id, user_id, debit_canonical_id, credit_canonical_id, match_type, confidence, resolution_status, matched_at`. Enforce balanced pairs: every match must have exactly one debit and one credit posting.

**F12. Confidence scoring uses a composite score for promotion decisions.**  
*Source: Review A (primary)*  
A single weighted composite can hide a critical failure behind good scores on other dimensions.  
**Fix:** Multi-gate approach: each dimension (extraction, metadata, reconciliation, balance continuity, classification) has an independent threshold. Auto-promote only if ALL gates pass. Composite score is used only for review queue prioritization.

**F13. No per-bank observability.**  
*Source: Review B (primary), Review C (supporting)*  
Silent parser degradation (e.g., HDFC changes template) goes undetected until user complaints.  
**Fix:** Add Prometheus metrics: `extraction_success_total{bank, model, parser, task}`. Alert on per-bank success rate drop > 5% over rolling 7-day window. Add yield rate metric: expected rows vs extracted rows.

**F14. DLQ has no consumer.**  
*Source: Review A (primary)*  
Dead letter queue without a processing strategy is a job graveyard.  
**Fix:** Define DLQ consumer: auto-retry with alternate strategy once, then create an ops ticket. Alert on DLQ depth > 0. DLQ items must be visible in an ops dashboard.

**F15. PDF password transit through queue is insecure.**  
*Source: Review A (primary), Review C (supporting)*  
Password sits in Redis in plaintext between upload and worker pickup.  
**Fix:** Encrypt with a short-lived symmetric key per job. Alternatively, decrypt synchronously during upload and store only decrypted artifacts. Zeroize password from memory after use.

---

## 3. Consolidated LLM Architecture Assessment

### What All Reviews Agree On

- Deterministic parser → LLM fallback ordering is correct.
- Prompt versioning + model registry pinning per extraction attempt is mature.
- Zero-shot extraction underperforms; few-shot examples per bank are needed.
- Structured output enforcement (grammar-constrained decoding) is preferable to repair loops.
- Self-hosted GPU concurrency is a bottleneck that needs admission control.

### Strongest LLM Recommendation (Synthesized from All Reviews)

The architecture should implement a **three-tier extraction strategy**:

**Tier 1: Deterministic parser (cost: ~$0, latency: <5s)**  
For known bank templates. This should handle 60–70% of volume at maturity (top 10 Indian banks).

**Tier 2: Deterministic table extraction + small LLM semantic tagging (cost: ~$0.01, latency: <30s)**  
*This is Review C's strongest unique contribution.* Instead of sending raw text to a large LLM for full JSON extraction:
1. Use `pdfplumber`/`camelot` to extract a raw CSV/markdown table.
2. Send the table to a small 7B–8B model with the prompt: "Here is a table. Map columns to schema: [Date, Description, Debit, Credit, Balance]. Return the column mapping only."
3. Apply the mapping deterministically.
This reduces LLM output from thousands of tokens (full JSON array) to ~20 tokens (column indices), cutting GPU time by 10–50×.

**Tier 3: Full LLM extraction (cost: ~$0.50–1.00, latency: 2–5min)**  
For completely unsupported layouts where table detection fails. Use the largest available model with few-shot examples from similar bank layouts.

**Additional LLM improvements (agreed across reviews):**
- Use grammar-constrained decoding (llama.cpp grammar / vLLM guided decoding) instead of repair loops.
- Implement iterative extraction for long tables: "Extract rows 1–30, then stop" to avoid the "lazy LLM" truncation problem (Review C's unique insight).
- Store successful extractions as few-shot examples in pgvector, scoped to user + bank, for future RAG-style prompting.
- Add a pre-LLM difficulty scorer (tiny 1–3B model) that routes documents to the appropriate tier.

---

## 4. Consolidated Data Model Recommendations

### Confirmed Missing Tables (All Reviews Agree)

| Table | Purpose | Why Missing Is a Problem |
|---|---|---|
| `transfer_matches` | Track transfer pairs with confidence and status | Transfer matching on a column flag will silently corrupt ledger balances |
| `statement_period_coverage` | Track which accounts have statements for which periods | Users can't know "is my month complete?" |
| `sync_cursors` | Gmail pagination checkpoint | Crash during sync re-fetches everything |
| `institution_parser_support` | Track parser versions and coverage per bank | Can't monitor parser health or plan expansion |

### Confirmed Schema Fixes

1. **Add CHECK constraint on account/card exclusivity:** `(account_id IS NOT NULL AND card_id IS NULL) OR (account_id IS NULL AND card_id IS NOT NULL)` on `statements`, `normalized_transactions`, `canonical_transactions`.

2. **Enumerate `parse_status` as explicit enum:** `uploaded, classifying, extracting, validating, review_required, parsed, partial, failed`.

3. **Add `reviewer_user_id` and `override_reason_code`** to `normalized_transactions` for audit trail of human review decisions (Review B's unique contribution).

4. **Add `yield_rate`** (expected rows vs extracted rows) to `extraction_attempts` for quality monitoring (Review C's unique contribution).

### On Double-Entry Ledger (Adjudicated Disagreement)

Review C strongly recommends a full double-entry postings model before any code is written. Reviews A and B don't raise this.

**Verdict:** A full double-entry model is the theoretically correct answer for any financial system. However, HisabClub is a personal finance *tracker*, not an accounting system. Users don't need debits and credits to balance — they need accurate transaction history per account.

**Recommended approach:**
- For MVP: Keep `canonical_transactions` as-is but add `transfer_matches` with balanced-pair enforcement. This gives you transfer correctness without the complexity of a postings model.
- For Phase 2: If multi-currency, split transactions, or refund reconciliation becomes complex, migrate to a postings model. The `canonical_transactions` → `postings` migration is feasible because the canonical layer is clean.
- **Do not** start with double-entry and regret the complexity. **Do** design the canonical layer so migration is possible.

---

## 5. Consolidated Security Assessment

### Confirmed Critical Vulnerabilities

1. **PDF parsing sandbox is insufficient.** All reviews flag this. PDF parsing (pymupdf, pdfplumber, Tesseract) can be exploited via malformed PDFs (decompression bombs, SSRF, malicious macros). The `worker-doc` container must run with: dropped capabilities, no network access, gVisor or seccomp profiles, process-level memory/time limits.

2. **Gmail tokens in primary database.** A DB dump exposes persistent inbox access. Use envelope encryption: encrypt refresh token with a KMS-managed key or user-derived key. The encrypted blob is useless without the live KMS.

3. **No Row Level Security.** One missed WHERE clause = financial data leak between users. PostgreSQL RLS is defense-in-depth that catches application bugs.

4. **PDF password in queue plaintext.** Encrypt per-job or decrypt synchronously during upload.

### Additional Security Items (Unique Contributions)

- **Review C:** Signed URLs for PDF viewing need explicit short expiration (suggest 5 minutes). The API examples show no TTL.
- **Review C:** No mention of WAF, request body size limits, or PDF bomb protection at the API gateway level.
- **Review A:** If a hosted LLM endpoint is ever enabled, there must be an explicit user consent flow, data classification check, and per-request audit log.

---

## 6. Unified Prioritized Action Plan

### Before Any Code Is Written

| # | Action | Source | Effort | Impact |
|---|---|---|---|---|
| 1 | **Build gold dataset** (50 statements × 8 banks, ground truth for metadata + transactions) | Review B | 2 weeks | Validates entire extraction architecture |
| 2 | **POC: Tesseract vs PaddleOCR vs DocTR** on 30 real Indian bank scans | Reviews B, C | 3 days | Determines OCR stack for MVP |
| 3 | **POC: pdfplumber cross-page table stitching** on 15-page statements with page-spanning tables | All reviews | 2 days | Validates chunking strategy |
| 4 | **POC: LLM column-mapping approach** (Review C's Tier 2) vs full JSON extraction on 50 statements | Review C | 3 days | Could reduce GPU costs 10–50× |

### Fix Before MVP (Blocking)

| # | Action | Source | Effort |
|---|---|---|---|
| 5 | PostgreSQL-backed job state + Redis notification | Reviews A, C | 2 days |
| 6 | Atomic canonical promotion (single DB transaction) | All reviews | 1 day |
| 7 | Define transaction deduplication fingerprint algorithm | Review A | 2 days |
| 8 | Semantic statement fingerprinting (Level 2 dedup) | Review C | 1 day |
| 9 | Cross-page table stitching before LLM extraction | All reviews | 3 days |
| 10 | Statement versioning enforcement (single active version) | Review B | 1 day |
| 11 | Separate document_id from statement_id at upload | Review A | 1 day |
| 12 | Multi-gate confidence thresholds (not composite score) | Review A | 1 day |
| 13 | `transfer_matches` table + balanced pair enforcement | All reviews | 2 days |
| 14 | PostgreSQL Row Level Security on user-scoped tables | Reviews A, C | 2 days |
| 15 | PDF parser sandboxing (gVisor/seccomp, no network, memory limits) | Reviews A, C | 1 day |
| 16 | Gmail token envelope encryption | Reviews B, C | 1 day |
| 17 | PDF password encryption through queue | Reviews A, C | 1 day |
| 18 | Institution password pattern registry for Gmail sync | Review C | 2 days |
| 19 | Per-bank extraction success rate metrics + alerts | Reviews B, C | 1 day |
| 20 | DLQ consumer + ops dashboard | Review A | 1 day |

**Estimated total pre-MVP effort: ~25 engineering days** (on top of core feature development)

### Fix Before Production Scale (Phase 2)

| # | Action | Source |
|---|---|---|
| 21 | Few-shot examples per bank in extraction prompts | All reviews |
| 22 | Grammar-constrained decoding (llama.cpp/vLLM guided) | Reviews A, B |
| 23 | Iterative extraction loop for long tables | Review C |
| 24 | Per-user fair queuing for LLM jobs | Review A |
| 25 | Dynamic model routing based on document difficulty | Review B |
| 26 | Tiered storage (cold storage for evidence after promotion) | Review A |
| 27 | Evaluate Temporal for extraction saga orchestration | Review B |
| 28 | Yield rate metric (expected vs extracted rows) | Review C |
| 29 | Partial promotion (high-confidence rows promoted, low-confidence quarantined) | Review C |
| 30 | UPI failure auto-reconciliation | Review C |

### Can Wait (Phase 3+)

- Double-entry postings model (only if transfer complexity demands it)
- Account Aggregator (AA/Sahamati) integration
- Full tax filing workflows
- ClickHouse for time-series analytics
- AI agentic insights
- Android SMS companion
- WhatsApp statement forwarding

---

## 7. POCs That Should Run This Week

| POC | What It Validates | Success Criteria |
|---|---|---|
| **30 real scans through OCR comparison** | OCR stack choice | PaddleOCR achieves >90% character accuracy on public-sector bank scans |
| **Cross-page table stitching** | Chunking strategy | Zero dropped/duplicated rows on 15-page statements |
| **LLM column-mapping vs full extraction** | GPU cost model | Column-mapping approach achieves >95% accuracy at <10% of GPU cost |
| **Redis kill during processing** | Job durability | With PostgreSQL-backed jobs, all in-flight work recovers automatically |
| **Same statement uploaded twice from net banking** | Dedup strategy | Semantic fingerprint catches the duplicate; SHA-256 does not |
| **10 concurrent extractions on target GPU** | Concurrency model | Measure actual throughput and queue backlog; define admission control parameters |

---

## 8. Summary of Review Quality

| Dimension | Review A (this conversation) | Review B | Review C |
|---|---|---|---|
| **Strongest area** | Concurrency, durability, tenant isolation, operational failure modes | LLM prompt/model optimization, observability, cost strategy | Real-world Indian banking edge cases, dedup flaws, practical extraction optimization |
| **Unique contributions** | RLS, job reaper, trace propagation through queues, premature statement_id | PaddleOCR recommendation, per-bank heat maps, Temporal suggestion | Password vault, column-mapping LLM strategy, SHA-256 dedup failure, double-entry advocacy, EMI/forex edge cases |
| **Blind spots** | Didn't catch Gmail password problem, didn't challenge OCR stack | Overstates Temporal urgency for MVP, didn't catch concurrency control gap | Overstates double-entry urgency, some recommendations are expensive for MVP stage |

All three reviews are strong. The synthesis above takes the best from each while resolving the conflicts with reasoning appropriate for a pre-MVP fintech system that must ship correctly but also ship soon.
