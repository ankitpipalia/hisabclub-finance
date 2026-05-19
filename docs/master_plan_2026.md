# HisabClub Master Plan 2026 — Audit, Refactor, Tax Engine, Connectors, AI, UX, Testing, and 100+ Feature Roadmap

> **Repository:** `/home/ankit/Documents/personal-finance-app`
> **Status:** Living document. Updated as phases land. Implementation order is given in §26.

---

## 0. Why This Plan Exists

HisabClub today is a privacy-first Indian personal-finance ledger with: deterministic + LLM hybrid PDF parsing, Gmail connector, SMS connector (Android-native module), durable parser jobs with DLQ, RLS-isolated multi-tenant Postgres, a typed extraction layer (`app/extraction/`) with dedup + balance-walk validation, a confidence-gated promotion pipeline, web (React+Vite) and mobile (Expo/RN) apps, and ~58 backend test files. Phase 2 has shipped the structural foundation: accounts, onboarding, statements review, net worth, subscriptions, tax verification, split lineage, persistent conversations.

The gap between today's product and the **"personal CA replacement"** vision is now mostly *quality, coverage, and correctness*, not raw structure. The audit surfaces three classes of work:

1. **Correctness leaks** — bypass paths (SMS, review-resolve, manual approve, legacy merger) skip the typed validator.
2. **Vertical depth gaps** — tax engine is a regex-on-merchant aggregator; document intelligence covers ~5 of ~25 personal-tax-relevant document types; AIS/26AS/Form-16 reconciliation is parser-only without cross-ledger matching; no FY-versioned tax-rule knowledge base.
3. **UX & connector polish** — no animation library, no skeletons/toasts, `window.confirm()` for destructive flows on some pages, no historical-Gmail incremental cursor exposed in UI, no SMS-to-statement matching, no CA export, no missing-document checklist UI.

This plan addresses all three across 11 phases, with a 100+ feature roadmap and a hard scope boundary: **non-business Indian personal income tax only.**

---

## 1. Executive Summary

| Pillar | Current | Target |
|---|---|---|
| Personal CA replacement | regex tax-planning, parsers for AIS/26AS/Form-16 metadata | FY-versioned tax engine, AIS/TIS/26AS/Form-16/Form-16A cross-reconciliation against ledger, ITR pack export, regime comparator, deduction optimizer with evidence trail |
| Expense ledger | mature: dedup, transfers, UPI reconciliation, EMI detection, anomaly, recurring | + split UX, NL search v2, statement coverage map, missing-tx from balance gaps |
| Gmail | OAuth + sender allowlist + attachment download + password resolution + cursor | + sender discovery wizard, inline-image password OCR, FY-aware historical scan, retry queue UI, scheduled scan UI |
| SMS | Android-native, batch import with dedup, basic regex; typed validation gated behind flag | typed validation on by default; statement↔SMS matching; pending-tx state; ATM/EMI/refund classifiers; on-device pre-filter |
| Document intelligence | bank/CC PDFs + AIS/26AS/Form-16 metadata parsers | 25+ doc types with FY mapping + evidence-linked extraction + review workspace v2 |
| AI/LLM | Qwen3.6-27B + Qwen3-VL, prompt-versioned, schema-validated, sanitized, RAG | model router by task tier, tax-rule RAG, eval harness, hosted/byok/self-host triad |
| UX | functional, ad-hoc CSS animations, partial toast/skeleton/modal coverage | motion library, skeletons, toasts, modals, accessibility, global FY selector, audit trail surfaces |
| Testing | 58 backend test files, sparse web/mobile, opt-in real-folder E2E | layered pyramid: unit + integration + golden snapshot + LLM eval + Playwright web E2E + Maestro mobile E2E + opt-in real-data smoke |
| Security/privacy | local-only mode, RLS, encrypted tokens | DPDP-aligned consent, audit log, data export/delete UX, cloud-LLM explicit opt-in banner |
| Self-hosting | docker-compose + shared local LLM | hosted SaaS ↔ BYOK LLM ↔ self-host parity, distinct UX modes |

---

## 2. Product Vision (Plain Language)

HisabClub is the **personal CA + financial brain** for a salaried/non-business Indian individual. The user lets HisabClub read their statements, Form-16/16A, AIS, 26AS, TIS, salary slips, mutual fund CAS, demat reports, rent receipts, insurance proofs, loan certificates. The system:

- builds a multi-year ledger across every account/card/UPI/SMS source;
- reconciles AIS/26AS line items against the ledger and flags mismatches;
- estimates tax under both regimes with the *right rules for the right FY*;
- recommends legal tax-saving actions with cited rule basis;
- generates a CA hand-off pack (CSV/PDF/JSON);
- explains every conclusion with linkable evidence (statement page, AIS entry, SMS, document chunk).

**Out of scope** (and stays out): GST, business books, TDS-return filing, payroll, audit, company compliance. Family/shared mode is allowed only as a personal-finance concept.

---

## 3. Current Product Map

### 3.1 Repo topology

```
backend/app/
  api/v1/        21+ routers
  engines/
    account/  auth/  gmail/  insights/  intake/  jobs/  ledger/  llm/  parser/  policy/  storage/  tax/
  extraction/    typed pipeline (RawTransaction, validator, promoter, dedup_key)
  models/        37 models
  alembic/versions/   ~20 migrations including RLS hardening
frontend/src/    Vite + React, 19 pages
mobile/src/      Expo/RN, 17 screens + native sms-reader module
```

### 3.2 Backend APIs (verified)

`upload.py` 1125 LOC, `transactions.py` 723 LOC, `statements.py` 605 LOC, `gmail.py` 311 LOC, `tax.py` 298 LOC, `insights.py` 293 LOC, `reviews.py` 306 LOC, `imports.py` 241 LOC, `sms.py` 234 LOC, `conversations.py` 228 LOC, `transfers.py` 147 LOC, `net_worth.py` 128 LOC, plus accounts/auth/categories/merchants/bills/budgets/export/assistant/subscriptions.

### 3.3 Engines

- **`parser/`** deterministic templates for HDFC/SBI/Axis/BoB savings + HDFC/SBI/Axis CC + generic stubs; password resolver with FY-aware DOB/PAN/mobile patterns; OCR fallback; statement lifecycle.
- **`llm/`** text + vision client, router by task tier, prompts versioned, sanitizer (preserves UTR/UPI refs near keywords), document classifier, statement classifier, transfer classifier, correction chat, knowledge retrieval (Postgres-backed RAG), iterative chunking with overlap, schema-enforced JSON mode.
- **`extraction/`** `RawTransaction` typed model, `validate_transaction()` with confidence tiers, `dedup_key()`, `promote_validated_batch()`, balance-walk.
- **`ledger/`** `DedupEngine` 3-tier, merchant normalization, transfer reclassifier, UPI reconciliation, transaction nature inference.
- **`insights/`** anomaly, bill, monthly summary, net worth, recurring, statement integrity, subscriptions, tax compliance, tax planning.
- **`intake/`** folder importer (recursive, per-file commit, RLS-aware), document classifier, tax-document parser.
- **`tax/`** AIS/Form-16/26AS metadata parsers + cross-verification stub.
- **`jobs/`** Postgres-backed durable jobs, per-user fair queue, DLQ, retry, parser state machine.
- **`gmail/`** OAuth flow, message fetch, attachment download, password pattern resolution, encrypted token storage.

### 3.4 Web (`frontend/src/pages/`)

19 pages: Dashboard, Upload, Transactions, TransactionDetail, Statements, StatementReview, Insights, Budgets, Bills, Tax, Assistant, Account, Accounts, Onboarding, Gmail, Imports, Login, ResetPassword, NetWorth, Subscriptions.

### 3.5 Mobile

17 screens; native Android `sms-reader`; `sms/` pipeline with `SmsBridge`, `SmsFilterer`, `SmsParser`, `SmsSyncService`, `bankPatterns.ts`.

### 3.6 Data model

37 tables. Key for plan: `users`, `accounts`, `statements`, `raw_pdfs`, `raw_sms`, `parsed_transactions`, `canonical_transactions` (full extraction audit columns), `transaction_splits`, `transaction_sources`, `transfer_matches`, `review_tasks`, `tax_portal_data`, `document_artifacts`, `document_knowledge_chunks`, `institution_password_pattern`, `connected_accounts`, `sync_cursor`, `balance_snapshots`, `statement_period_coverage`.

---

## 4. User Personas

| Persona | Profile | Top jobs |
|---|---|---|
| Salaried Sailesh | 30, IT, ₹25L CTC, savings + 2 CCs + ELSS + NPS + home loan | auto-import, regime comparison, 80C/24(b)/80D tracking, ITR pack for CA |
| Multi-bank Meera | 38, 4 banks, 3 CCs, FDs, MF SIPs, parents' health insurance | reconcile across banks, dedup transfers, anomaly alerts, missing-statement detection |
| NRI-ish Niraj | recent move abroad, lingering NRO + capital gains | residency-aware regime, capital-gains import |
| Privacy-Priya | 32, lawyer, hates cloud, self-hosts everything | full local mode, no Gmail OAuth, self-host Postgres + local Qwen |
| Freelance-Faisal | 28, freelancer | personal flows only; punt ITR-3/4 to a CA but organize statements |

Out-of-persona (excluded): GST-registered businesses, companies, partnerships.

---

## 5. Current Feature Inventory

**Implemented (verified):** PDF upload + durable parsing, OCR fallback (flagged), vision LLM (flagged), schema-validated JSON extraction with chunking, sanitizer preserving UTR/UPI refs, deterministic parsers for 8 bank/CC templates, password-pattern store + resolver, statement semantic dedup, dedup_key transaction dedup, balance-walk for savings, transfer reclassification, UPI reconciliation, transaction nature inference, EMI/recurring detection, anomaly detection, monthly summary, net-worth overview, subscriptions, statement integrity, tax-compliance items, tax-planning regex, AIS/26AS/Form-16 metadata parsing + cross-verification stub, Gmail OAuth + sync, SMS batch import (Android), review tasks, statement review UI, transaction split, conversations/assistant, password reset, data reset, RLS hardening, cold storage tiering, folder import.

**Partial:** Tax engine, AIS/26AS reconciliation, Form-16 cross-check, capital gains, deductions optimizer, Gmail historical-scan UX, SMS-statement matching, missing-document checklist, CA export pack, animations/skeletons/toasts on all pages, frontend tests, mobile tests, LLM eval harness, hosted-LLM opt-in UX, iOS build assets.

**Missing:** ELSS/MF CAS parser, broker P&L parser, EPF/PPF/NPS statement parsers, insurance receipt parser, rent receipt + agreement parser, donation receipt parser, challan parser, notice/intimation parser, ITR form recommender, advance-tax estimator, refund tracker, family/shared mode, on-device SMS pre-filter, audit log, data export/delete UX, DPDP-aligned consent.

---

## 6. Current Gaps & Critical Risks

### 6.1 Correctness

| ID | File:line | Risk |
|---|---|---|
| W1.1 | `engines/ledger/merger.py` | `promote_to_canonical` requires explicit kwargs to preserve audit (now supported but caller-dependent) |
| W1.2 | `api/v1/sms.py` | typed validator flag still default-off; legacy bypass remains |
| W1.3 | `api/v1/reviews.py:151` | resolve+promote passes hardcoded `validation_status="valid"` |
| W1.4 | `engines/ledger/dedup.py` | (verified fixed) Decimal comparison in tiers 2/3 |
| W1.5 | `extraction/validator.py` + `extraction/promoter.py` | (verified fixed) `BalanceWalkProblem` stable identity |
| W1.6 | `extraction/promoter.py:84` | `is_credit is None` only routed to review when flag enabled (off by default) |
| W1.7 | `engines/llm/parse_fallback.py` | (verified fixed) chunk failures surfaced in `llm_chunk_errors` |
| W1.8 | `engines/llm/sanitizer.py` | flag-gated UPI/UTR preservation, currently off |
| W1.9 | `engines/parser/validation.py` vs `extraction/validator.py` | dual validation pipelines persist |

### 6.2 Tax-engine gaps

- No FY-keyed rules table (slabs, std deduction, 87A, surcharge, cess); only `_NEW_REGIME_CONFIG_BY_FY_START` in `engines/insights/tax_compliance.py`.
- `tax_planning.py:_RULES` is 8 regex rules matched against category+merchant. Section limits, joint deductions (80CCD ceiling), 80D age-stratified caps, HRA, home-loan interest split (self-occupied vs let-out), capital gains classification — none implemented.
- No regime comparator.
- No AIS/26AS ↔ ledger reconciliation.
- No ITR-form recommender, no CA export pack.

### 6.3 Connector gaps

**Gmail:** sender-discovery is allowlist-only — no learning wizard. Password-from-inline-image OCR not wired. Historical-scan window not FY-aware. Retry queue not surfaced. Scheduled scan exists but no UI.

**SMS:** server-side typed validation flag exists but default off. No on-device pre-filter — full body of every SMS hits the server. No statement-confirmation matching. No promotional/spam server-side filter.

### 6.4 UX gaps

- No animation library on either platform.
- Some pages still use `window.confirm()`; toast/skeleton coverage incomplete.
- No FY selector globally.
- Audit trail exists in DB but not surfaced on mobile.
- iOS build incomplete (icons/splash, infoPlist).

### 6.5 Testing gaps

- Sparse frontend tests; near-zero mobile tests.
- No Playwright/Cypress, no Maestro/Detox.
- No LLM regression eval suite.
- No migration up/down test.
- No backup/restore test.

### 6.6 Privacy / compliance

- DPDP Act 2023 consent model not codified.
- No user-facing audit log.
- No "export all my data" / "delete my account" UX.
- Cloud-LLM warning banner missing.
- Threat model / data flow diagram not documented.

### 6.7 Performance risks

- `upload.py` 1125 LOC and `transactions.py` 723 LOC are monoliths.
- Vision LLM page limit 24; statements >24 pages get truncated.
- Knowledge retrieval embeddings without pgvector index tuning.
- Frontend bundle not measured.

---

## 7. Architecture — Phased Change Shape

```
Phase 0  Plan & Safety       (this doc)
Phase 1  Correctness         W1.x leaks + bypass removal + flag flips
Phase 2  Tax Engine          FY rules registry + regime calc + reconciliation v1 + ITR + CA export
Phase 3  Connectors          Gmail wizard, retry UI, img-OCR password; SMS validation + statement matching
Phase 4  Document Intel      12 new parsers + review workspace v2
Phase 5  AI/LLM Hardening    eval harness, hosted/byok/self-host triad, tax-rule RAG
Phase 6  UX Overhaul         motion lib, skeletons, toasts, modals, FY selector, iOS assets
Phase 7  Test Harness        Vitest/Playwright, Jest/Maestro, LLM eval CI gate, migration tests
Phase 8  Performance         router decomposition, bundle splitting, pgvector tuning
Phase 9  Production Readiness observability, DPDP consent, data export/delete, self-host bootstrap
Phase 10 Long-tail features  remaining P2/P3 by priority
```

---

## 8. 100+ Feature Roadmap

> Each feature includes priority (P0–P3), complexity (S/M/L/XL), and status (Missing/Partial/Improve).

### 8.1 Tax planning (15)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 1 | FY-versioned rules table (FY23-24, 24-25, 25-26) | Missing | P0 | M |
| 2 | Old vs New regime side-by-side with break-even | Missing | P0 | M |
| 3 | 80C utilization tracker (₹1.5L) itemized | Partial | P0 | M |
| 4 | 80CCD(1B) NPS additional ₹50k | Missing | P0 | S |
| 5 | 80CCD(2) employer NPS (only new regime) | Missing | P1 | S |
| 6 | 80D age-stratified caps | Partial | P0 | M |
| 7 | 80E education loan interest | Improve | P1 | S |
| 8 | 80G donations 50%/100% with/without cap | Missing | P1 | M |
| 9 | 80GG rent paid when no HRA | Missing | P2 | S |
| 10 | 80TTA/80TTB savings/FD interest | Partial | P1 | S |
| 11 | 24(b) home-loan interest split | Missing | P0 | M |
| 12 | HRA calculator | Missing | P0 | M |
| 13 | Capital gains classification (equity, debt, REIT/InvIT, gold, RE, VDA) | Missing | P1 | L |
| 14 | Advance-tax estimator | Missing | P2 | M |
| 15 | ITR form recommender (ITR-1/2/3/4) | Missing | P0 | M |

### 8.2 Tax filing preparation (10)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 16 | CA export pack (CSV+JSON+PDF) | Missing | P0 | M |
| 17 | Missing-document checklist per FY | Missing | P0 | M |
| 18 | Form-16 ↔ bank salary credits reconciliation | Missing | P0 | L |
| 19 | Form-16A ↔ interest/dividend TDS reconciliation | Missing | P1 | M |
| 20 | 26AS line-item ↔ ledger match | Missing | P0 | L |
| 21 | AIS line-item ↔ ledger match | Missing | P0 | L |
| 22 | TIS variance highlighter | Missing | P1 | M |
| 23 | Refund/demand tracker | Missing | P2 | M |
| 24 | Notice/intimation parser + tracker | Missing | P2 | M |
| 25 | Belated/revised return reminder (Sec 139(4)/(5)) | Missing | P2 | S |

### 8.3 Gmail ingestion (10)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 26 | Sender discovery wizard | Partial | P0 | M |
| 27 | Historical FY-aware backfill scan | Partial | P0 | M |
| 28 | Inline-image password OCR | Missing | P1 | M |
| 29 | Password-pattern review UI | Missing | P0 | M |
| 30 | Scheduled scan UI | Partial | P1 | S |
| 31 | Retry queue UI with reason codes | Missing | P1 | M |
| 32 | Attachment-only mode | Missing | P2 | S |
| 33 | IMAP/Outlook connector | Missing | P3 | XL |
| 34 | Local-only Gmail mode | Missing | P2 | L |
| 35 | Sender risk badges | Missing | P2 | S |

### 8.4 SMS ingestion (10)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 36 | Server-side typed validation default on (W1.2) | Partial | P0 | S |
| 37 | On-device pre-filter (bank/UPI/CC only) | Partial | P0 | M |
| 38 | SMS↔statement matching (pending→confirmed) | Missing | P0 | M |
| 39 | ATM cash withdrawal classifier | Missing | P1 | S |
| 40 | EMI / standing-instruction SMS classifier | Partial | P1 | S |
| 41 | UPI refund / failure SMS classifier | Missing | P1 | M |
| 42 | Promo/OTP/spam exclusion w/ confidence | Partial | P0 | S |
| 43 | iOS SMS workaround (share extension) | Missing | P3 | L |
| 44 | Bank-sender pattern library | Partial | P1 | M |
| 45 | Privacy explainer screen | Partial | P0 | S |

### 8.5 Document intelligence (12)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 46 | Mutual fund CAS parser (CAMS + KFintech) | Missing | P0 | L |
| 47 | Broker P&L parser (Zerodha/Groww/Upstox) | Missing | P0 | L |
| 48 | EPF passbook parser | Missing | P1 | M |
| 49 | PPF statement parser | Missing | P1 | M |
| 50 | NPS Tier-1/2 statement parser | Missing | P1 | M |
| 51 | Insurance premium receipt parser | Missing | P1 | M |
| 52 | Home-loan interest certificate parser | Missing | P0 | M |
| 53 | Rent receipt + agreement parser | Missing | P1 | M |
| 54 | Donation receipt parser (80G) | Missing | P2 | M |
| 55 | Tuition fee receipt parser (80C) | Missing | P2 | S |
| 56 | Tax challan parser (ITNS 280/281) | Missing | P1 | M |
| 57 | Notice/intimation classifier + parser | Missing | P2 | L |

### 8.6 Expense management (10)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 58 | Split-transaction UX v2 | Partial | P1 | M |
| 59 | Natural-language search v2 | Partial | P1 | M |
| 60 | Statement coverage map | Missing | P1 | M |
| 61 | Missing-transaction detection from balance gaps | Partial | P1 | M |
| 62 | Duplicate-transaction explainer panel | Missing | P2 | S |
| 63 | Tags + notes + attachments per transaction | Partial | P2 | M |
| 64 | Family/shared mode | Missing | P2 | L |
| 65 | Cashflow forecast | Missing | P2 | M |
| 66 | Lifestyle-inflation detector | Missing | P3 | M |
| 67 | Abnormal-spend alerts (push) | Missing | P2 | M |

### 8.7 Investments / loans / insurance (10)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 68 | Portfolio view aggregating all holdings | Missing | P1 | L |
| 69 | XIRR per holding | Missing | P2 | M |
| 70 | Goal tracker | Missing | P3 | M |
| 71 | EMI schedule view with prepayment what-if | Missing | P1 | M |
| 72 | Credit-card statement summary | Partial | P1 | M |
| 73 | Premium-renewal reminder | Missing | P2 | S |
| 74 | Sum-assured aggregator | Missing | P3 | S |
| 75 | Maturity ladder (FD/PPF/NSC) | Missing | P2 | M |
| 76 | Health-insurance gap analysis | Missing | P3 | M |
| 77 | NPS tier allocation viewer | Missing | P3 | S |

### 8.8 AI assistant (8)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 78 | Grounded Q&A with evidence | Partial | P1 | M |
| 79 | "Explain why this tx is classified" | Missing | P1 | M |
| 80 | "What if I top up 80C by ₹X" | Missing | P0 | M |
| 81 | "Where am I missing receipts?" | Missing | P0 | M |
| 82 | Tool-using assistant | Missing | P2 | L |
| 83 | Conversation export | Missing | P3 | S |
| 84 | Learning loop (corrections → rules) | Partial | P1 | M |
| 85 | Hosted vs local LLM badge | Missing | P0 | S |

### 8.9 Review workflow (5)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 86 | Review workspace v2 (PDF + extracted + validator diff) | Partial | P0 | L |
| 87 | Bulk approve with filters | Partial | P1 | M |
| 88 | Audit-trail view on canonical | Partial | P1 | M |
| 89 | "Why did the LLM say this?" | Missing | P2 | M |
| 90 | Re-review with different model | Partial | P2 | M |

### 8.10 Privacy / security / self-hosting (8)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 91 | DPDP-aligned consent screen | Missing | P0 | M |
| 92 | Cloud-LLM warning + opt-in toggle | Missing | P0 | S |
| 93 | Audit log | Partial | P1 | M |
| 94 | Data export (zip) | Missing | P0 | M |
| 95 | Data deletion (full purge) | Partial | P0 | M |
| 96 | Backup encryption for self-host | Missing | P2 | M |
| 97 | Self-host one-command bootstrap | Partial | P1 | M |
| 98 | Threat model + data-flow diagram | Missing | P1 | M |

### 8.11 Mobile UX (5)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 99 | iOS build assets | Partial | P0 | M |
| 100 | Reanimated 3 integration | Missing | P1 | M |
| 101 | Offline-first sync queue | Missing | P2 | L |
| 102 | Push notifications | Missing | P2 | M |
| 103 | App-lock biometric gate | Missing | P1 | S |

### 8.12 Web UX (5)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 104 | Global FY selector | Missing | P0 | S |
| 105 | Toast system everywhere | Partial | P0 | S |
| 106 | Skeleton states everywhere | Partial | P0 | M |
| 107 | Confirm modal everywhere | Partial | P0 | S |
| 108 | Indian language stubs (Hindi first) | Missing | P3 | M |

### 8.13 Testing / observability / DevOps (10)

| # | Feature | Status | P | C |
|---|---|---|---|---|
| 109 | Vitest + RTL on web (broad) | Partial | P0 | L |
| 110 | Playwright web E2E | Missing | P0 | L |
| 111 | Jest + RTL on mobile (broad) | Partial | P1 | L |
| 112 | Maestro mobile E2E | Missing | P1 | L |
| 113 | LLM regression eval CI gate | Missing | P0 | L |
| 114 | Real-data smoke (FY24-25) PII-redacted | Partial | P0 | M |
| 115 | Migration up/down test in CI | Missing | P1 | M |
| 116 | OpenTelemetry + Prometheus + Grafana | Missing | P1 | L |
| 117 | Sentry opt-in error monitoring | Missing | P2 | S |
| 118 | Synthetic fixture generator from real folder | Missing | P1 | M |

**Total: 118 features.**

---

## 9. Refactor Plan

### 9.1 Single-source validator

After Phase 1 lands, delete `engines/parser/validation.py` permissive path (after moving useful heuristics into `extraction/validator.py` as warnings). Make `validate_transaction()` the only writer of `validation_status`/`validation_errors` on `CanonicalTransaction`. Plumb explicit kwargs through `promote_to_canonical()` and require all callers to pass them.

### 9.2 Router decomposition

- Split `api/v1/upload.py` (1125 LOC) → `upload.py`, `upload_status.py`, `upload_jobs.py`, `upload_password.py`.
- Split `api/v1/transactions.py` (723 LOC) → list/detail/bulk/split.
- Split `api/v1/statements.py` (605 LOC) → list/review/lifecycle.

### 9.3 Tax engine package

```
engines/tax/
  rules/
    fy_2023_24.py
    fy_2024_25.py
    fy_2025_26.py
    registry.py
  regime.py
  deductions.py
  hra.py
  capital_gains.py
  reconcile/
    form16.py
    form_16a.py
    form_26as.py
    ais.py
    tis.py
  recommender/
    itr_form.py
    optimizer.py
  export/
    ca_pack.py
```

### 9.4 LLM router clarity

Rename `engines/llm/router.py` to expose a `LLMTier` enum (`small`, `default`, `large`, `vision`, `embedding`) and route per-task; add tier overrides via config and per-user setting.

### 9.5 SMS path

Promote `mobile/src/sms/SmsFilterer.ts` patterns to a server-shared `engines/intake/sms_patterns.py` so on-device filter and server validator agree.

---

## 10. Tax Knowledge System Plan

### 10.1 FY rules registry

`engines/tax/rules/registry.py` exposes `get_rules(fy: str) -> TaxRules`. Each FY module is a pure-data file with citation comments.

### 10.2 Regime calculator

`engines/tax/regime.py` — `compute_old_regime(fy, inputs)`, `compute_new_regime(fy, inputs)`, `compare(fy, inputs)`.

### 10.3 Reconciliation engines

`engines/tax/reconcile/form16.py`, `form_26as.py`, `ais.py`, `tis.py` — match against ledger; emit `ReviewTask` for unmatched ≥ threshold.

### 10.4 Optimizer

`engines/tax/recommender/optimizer.py` — "if user adds ₹X to 80C/80CCD(1B)/80D, savings under each regime."

### 10.5 CA export

`engines/tax/export/ca_pack.py` zip with `summary.pdf`, `ledger_FY.csv`, `regime_comparison.json`, `deduction_breakup.csv`.

---

## 11. Data Model Plan

### 11.1 New tables

| Table | Purpose |
|---|---|
| `tax_rules_runtime_overrides` | per-user override (e.g., HRA city tier) |
| `ais_line_items` | normalized AIS rows |
| `form26as_line_items` | normalized 26AS rows |
| `tax_reconciliation_matches` | AIS/26AS rows ↔ canonical_transactions |
| `investment_holdings` | aggregate portfolio |
| `loan_accounts` | EMI metadata |
| `insurance_policies` | premium + cover |
| `rent_records` | HRA evidence |
| `audit_log` | immutable append-only |

### 11.2 Existing changes

- `canonical_transactions`: add nullable `fy_code` + index `(user_id, fy_code)`.
- `connected_accounts`: add `last_scan_completed_at`, `last_scan_window_start`/end, `password_resolve_failures_json`.

### 11.3 Integrity constraints

- CHECK: `canonical_transactions.amount > 0`.
- CHECK: `direction IN ('debit','credit')`.
- CHECK: `extraction_source IN ('template','llm','ocr','sms','manual','reconciliation','split_child')`.

---

## 12. API Plan

New endpoints (selected):

| Endpoint | Use |
|---|---|
| `GET /api/v1/tax/regime/compare?fy=` | regime side-by-side |
| `POST /api/v1/tax/regime/inputs` | user-overridable inputs |
| `GET /api/v1/tax/checklist?fy=` | missing-document checklist |
| `GET /api/v1/tax/reconciliation/form16?fy=` | F16 reconcile |
| `GET /api/v1/tax/reconciliation/26as?fy=` | 26AS reconcile |
| `GET /api/v1/tax/reconciliation/ais?fy=` | AIS reconcile |
| `GET /api/v1/tax/itr-recommendation?fy=` | ITR pick |
| `POST /api/v1/tax/optimizer/whatif` | what-if scenario |
| `GET /api/v1/tax/export/ca-pack?fy=` | streaming zip |
| `GET /api/v1/gmail/wizard/senders` | sender discovery |
| `POST /api/v1/gmail/wizard/allowlist` | one-click allowlist |
| `GET /api/v1/gmail/password-patterns` | review UI |
| `POST /api/v1/sms/match` | SMS-statement matching |
| `GET /api/v1/account/export` | data export (zip) |
| `DELETE /api/v1/account` | account purge with confirm |
| `GET /api/v1/insights/coverage-map?fy=` | calendar heatmap |

---

## 13. Web UX Plan

- Install **Framer Motion** (~30KB gz) or stay CSS-only with motion tokens.
- Toast: **react-hot-toast** OR continue with internal Toast primitive.
- Skeleton: existing `Skeleton` primitive.
- Modal: existing `ConfirmDialog`.
- Global `FYContext` provider in `App.tsx`.

Per-page focus: Dashboard (FY-scoped tiles, tax-readiness widget), Tax (regime comparator, deduction trackers, what-if slider, CA export), StatementReview (confidence badges, evidence popover), Gmail (sender wizard, password-pattern card, retry queue), Assistant (hosted/local LLM badge), Account (data export/delete, LLM mode picker, consent toggle).

---

## 14. Mobile UX Plan

- **Reanimated 3** + **react-native-gesture-handler**.
- **expo-haptics** for confirmations.
- **expo-local-authentication** for app-lock.
- iOS build: icons, splash, infoPlist.
- Mobile FY selector parity.
- SMS sync: redesign permission screen with per-bank preview.
- New screens: TaxRegime, MissingDocs, CaExport.

---

## 15. AI/LLM Plan

### 15.1 Triad

```
mode = "hosted" | "byok" | "local"
```

- **hosted** OFF by default; gated by consent + warning banner.
- **byok** user's API key; sanitizer + redaction enforced.
- **local** shared local LLM (current default); Qwen3.6-27B Q5.

### 15.2 Task tiers

| Tier | Default model | Tasks |
|---|---|---|
| small | local Qwen 7B/14B | classification, short categorization |
| default | Qwen3.6-27B Q5 | extraction fallback, correction chat, knowledge |
| large | reserved (hosted only) | rare hard documents |
| vision | Qwen3-VL 8B Q4 | page-image, inline-image password |

### 15.3 Eval harness

`backend/tests/llm_eval/` — golden inputs → expected JSON. Nightly CI run scores accuracy + drift.

### 15.4 Tax-rule RAG

Index `engines/tax/rules/fy_*.py` + curated CBDT excerpts. Retrieve during assistant Q&A.

### 15.5 Redaction proof

Every outbound LLM payload runs through `engines/llm/sanitizer.py` and is logged (hash + size + redactions count).

---

## 16. Gmail/Email Connector Plan

### 16.1 Sender discovery wizard

`POST /api/v1/gmail/wizard/senders` returns top-100 distinct senders in last FY+1 window scored by financial-likelihood heuristics. UI lets user one-click allowlist.

### 16.2 Password resolution

- Inline-image OCR via vision LLM.
- Pattern learning when manual password succeeds.
- Failure surfacing in `connected_accounts.password_resolve_failures_json` and a `ReviewTask`.

### 16.3 Incremental cursor

Expose `last_history_id`, `last_message_id`, `last_scan_completed_at` in API and UI.

### 16.4 Scheduled scan

Per-account cron (`daily 03:00 IST` default) via job runner.

---

## 17. SMS Connector Plan

### 17.1 Server-side typed validation

- Default-enable `sms_typed_validation_enabled`.
- Adapt `RawSms` → `RawTransaction` via `extraction/adapter.dict_to_raw_transaction(source=ExtractionSource.SMS)`.
- Validate via `validate_transaction()`.
- Promote with explicit `validation_status`/`validation_errors`.
- Quarantine `LOW_CONFIDENCE`/`NEEDS_REVIEW`; create review task with `statement_id=None`.

### 17.2 On-device pre-filter

Move `mobile/src/sms/SmsFilterer.ts` logic into a shared rule set in `engines/intake/sms_patterns.py` exported as JSON consumed by mobile.

### 17.3 SMS↔statement matching

`engines/ledger/sms_statement_match.py` — for each `RawSms` row, scan `canonical_transactions` ±3-day window for unmatched candidate. Match → SMS confirmed + canonical row stores `evidence_sms_id`. Unmatched after 7 days + high confidence → SMS becomes candidate canonical (review task).

### 17.4 Classifiers

ATM cash, EMI auto-debit, UPI refund/failure as additional shared patterns.

---

## 18. Document Intelligence Plan

For each of the 12 new parsers:

1. `engines/intake/<doc>_parser.py` deterministic-first + LLM fallback with doc-specific schema.
2. Metadata into a typed table.
3. Transactions/income/deductions back-feed canonical ledger.
4. FY mapping for tax engine.

Review workspace v2 extends `StatementReviewPage` for non-statement docs with tabs.

---

## 19. Testing & Validation Strategy

### 19.1 Pyramid

```
Real-data smoke    RUN_REAL_E2E=1, FY24-25 folder, PII-redacted snapshots
Playwright web E2E + Maestro mobile E2E
API integration (pytest, in-memory Postgres)
LLM eval golden (nightly + PR gate)
Unit tests: backend 80%+, web/mobile 60%+
```

### 19.2 LLM eval harness

`backend/tests/llm_eval/` — fixture pairs `(prompt_input.json, expected_output.json)`. Schema-valid + field-level match + cosine-sim on description. ≥95% pass for release.

### 19.3 Real-data smoke

Already gated by `RUN_REAL_E2E=1`. Extend to per-bank smoke and Form-16+AIS upload.

### 19.4 Migration tests

`backend/tests/test_migrations/test_up_down.py` — apply migrations, downgrade, re-upgrade on PR.

### 19.5 PII redaction tests

Assert LLM payloads in sanitizer mode contain no PAN/Aadhaar/card-number/account-number tokens.

---

## 20. Security & Privacy Plan

### 20.1 Threat model (`docs/threat_model.md`)

Actors: signed-in user; rogue user across tenants; cloud LLM provider (opt-in); SaaS admin; device thief; compromised Gmail token.

### 20.2 DPDP alignment

- Consent screen on first sign-in.
- Settings exposes export + delete + per-purpose opt-in.
- Audit log records every consent change.

### 20.3 Key management

`data_encryption_key` rotation runbook + self-host generation guide.

### 20.4 Cloud-LLM banner

When user enables `mode='hosted'` or `mode='byok'`, modal warning.

---

## 21. Performance & Optimization Plan

| Target | Action |
|---|---|
| PDF parse p95 ≤ 30s | profile `engines/parser/base.py`; single-pass text extraction; knowledge cache |
| Vision parse p95 ≤ 90s | raise `llm_vision_page_limit` to 36 with chunking; pipeline render+infer |
| Frontend FCP < 1.5s | Vite code-split per route; preload fonts; lazy `react-pdf` |
| Mobile cold start < 2.5s | reduce bundle; lazy `sms-reader` Android-only |
| API p95 < 250ms | `(user_id, fy_code, transaction_date)` index on `canonical_transactions`; pgvector ivfflat tuning |
| Job throughput | tune poll seconds, worker count |

---

## 22. DevOps & Release Plan

- Trunk-based; PR gates: pytest + lint + frontend build + LLM eval drift check.
- Releases: semver on backend container; EAS Build for mobile.
- **Self-host one-shot:** `make self-host-bootstrap` → docker-compose up, alembic upgrade head, seed institutions/categories, generate `data_encryption_key`, prompt for first user.

---

## 23. Observability Plan

- **Logs:** structured JSON; redaction guard; correlation_id.
- **Metrics:** Prometheus from FastAPI; key metrics: extraction_yield_rate, dedup_match_rate, sms_promotion_rate, gmail_password_resolve_rate, llm_latency_p95, job_queue_depth, review_task_backlog.
- **Traces:** OpenTelemetry spans across upload→parse→validate→promote.
- **Dashboards:** Grafana JSON in `docs/observability/dashboards/`.
- **Alerts (hosted enforced; self-host optional):** queue_depth > N, error_rate > X%, LLM endpoint unavailable.

---

## 24. Documentation Plan

- `docs/architecture.md` — replaces fragmented existing docs.
- `docs/tax_engine.md` — FY rule format, how to add an FY.
- `docs/connectors/gmail.md`, `docs/connectors/sms.md`.
- `docs/self_host.md` — full bootstrap.
- `docs/security/threat_model.md`.
- `docs/api/openapi.json` generated from FastAPI.

---

## 25. Migration & Rollback Plan

Every new migration:

1. Forward and backward tested in CI.
2. Uses `op.add_column(..., nullable=True)` then backfill then `nullable=False` for large tables.
3. Has a runbook entry for any data movement.
4. Destructive operations behind feature flag for one minor release before code deletion.

---

## 26. Implementation Phases

### Phase 0 — Plan & Safety (this commit)

Goal: commit plan + capture baseline.
Files: `docs/master_plan_2026.md` (this file).
Acceptance: plan merged.

### Phase 1 — Correctness (W1.x closure)

Goal: Close remaining W1.x leaks (W1.2, W1.3, W1.6 + flag flips for W1.8, W1.9 deprecation prep).
Files: `config.py`, `api/v1/sms.py`, `api/v1/reviews.py`, `extraction/promoter.py`, `engines/llm/sanitizer.py`, web `BudgetsPage.tsx`.
Tests: `test_api/test_sms_validation*.py`, `test_api/test_reviews_audit*.py`, `test_extraction/test_ambiguous_direction.py`.
Acceptance: no path writes `validation_status` without going through `validate_transaction()`; SMS quarantines low-confidence; reviews preserve audit; CI green.

### Phase 2 — Tax Engine

Goal: FY rules registry + regime calculator + reconciliation v1 + ITR recommender + CA export.
Files: new `engines/tax/`, `api/v1/tax.py` extensions, `schemas/tax.py` extensions, web `TaxPage.tsx`.
Tests: `test_tax/test_rules_fy*.py`, regime worked-examples, reconcile tests.
Acceptance: regime matches hand-computed; F16/26AS/AIS reconciliation emits sane match/diff lists.

### Phase 3 — Connectors

Goal: Gmail wizard + retry UI + img-OCR password; SMS server-validated + matching + on-device pre-filter.
Tests: mock Gmail tests; SMS matching tests; pattern parity.

### Phase 4 — Document Intelligence

Goal: 12 new parsers + review workspace v2.
Tests: per-parser golden fixtures.

### Phase 5 — AI/LLM Hardening

Goal: Triad mode + eval harness + tax-rule RAG.
Tests: `tests/llm_eval/` baseline.

### Phase 6 — UX Overhaul

Goal: Animation, skeletons, toasts, modals, FY selector, iOS assets.
Tests: Vitest snapshots.

### Phase 7 — Test Harness

Goal: Vitest+Playwright web E2E, Jest+Maestro mobile, LLM eval CI gate, migration up/down.

### Phase 8 — Performance

Goal: Hit perf targets from §21.

### Phase 9 — Production Readiness

Goal: Observability, DPDP consent, data export/delete, self-host bootstrap.

### Phase 10 — Long-tail features

P2/P3 items from §8.

---

## 27. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Tax rule changes mid-FY | M | M | FY modules pure-data + dated comments; nightly eval |
| LLM regression breaks extraction | M | H | LLM eval CI gate from Phase 5; prompt-version pinning |
| Real-data PII leaks in logs/snapshots | L | H | redaction tests; CI grep on PR diff |
| Migration deadlock on large tables | L | H | nullable-then-backfill |
| Gmail API quota | L | M | per-user backoff + retry queue |
| Vision LLM VRAM contention | M | M | text-primary path always available |
| Self-host UX confusion | M | M | one-command bootstrap |
| Phase 2 tax-engine accuracy disputes | M | H | every output cites FY + rule basis + source URL |

---

## 28. Definition of Done

Per feature:

1. Implementation merged with tests (unit + integration).
2. Tax-related: cited source comments + worked-example test cases.
3. LLM-touching: eval delta reported.
4. UI: skeleton + error + empty states; web + mobile parity if applicable.
5. Privacy-sensitive: redaction asserted in tests.
6. Docs updated.
7. Real-folder smoke green (where applicable).

---

## 29. First 30 Days

| Day | Deliverable |
|---|---|
| 1 | Plan committed. Baseline metrics captured. |
| 2-3 | Phase 1.1: flip `sms_typed_validation_enabled` default, remove legacy SMS bypass. Tests. |
| 4 | Phase 1.2: review-resolve audit preservation. Tests. |
| 5 | Phase 1.3: ambiguous CR/DR → review (flag default flip). Tests. |
| 6 | Phase 1.4: BudgetsPage `confirm()` → ConfirmDialog. |
| 7 | PR merged. Real-folder smoke run; capture deltas vs baseline. |
| 8-10 | Phase 2.1: FY rules registry (FY23-24, 24-25, 25-26). Slab math tests. |
| 11-12 | Phase 2.2: regime calculator. Worked-example tests. |
| 13-14 | Phase 2.3: deductions engine (80C/80CCD(1B)/80D/80E/80TTA/80TTB/HRA). |
| 15 | Phase 2.3 cont: capital gains v1 (equity STCG/LTCG). |
| 16-17 | Phase 2.4: `reconcile/form16.py` + API. |
| 18-19 | Phase 2.4 cont: `reconcile/form_26as.py` + API. |
| 20-21 | Phase 2.4 cont: `reconcile/ais.py` + API; TIS variance. |
| 22 | Phase 2.4 cont: `recommender/itr_form.py` decision tree + API. |
| 23 | Phase 2.4 cont: `recommender/optimizer.py` what-if + API. |
| 24 | Phase 2.4 cont: `export/ca_pack.py` zip generation + API. |
| 25 | Web TaxPage: regime comparator + checklist + CA export button. |
| 26 | PR raised for Phase 2; CI + LLM eval green. |
| 27 | Phase 2 merged. Phase 3 starts: Gmail wizard scaffold. |
| 28 | Gmail sender discovery + allowlist API. |
| 29 | Password-pattern review UI. |
| 30 | Inline-image OCR for password hints; PR raised. |

---

---

## Implementation Status (2026-05-20)

| Phase | Status | Notes |
|---|---|---|
| Phase 0 | ✅ shipped | This master plan committed (commit `71f883f`). |
| Phase 1 | ✅ shipped | SMS bypass removed (flag default `True`); review-resolve audit preserved (user_override stamp + payload_json breadcrumb); ambiguous CR/DR default-route to review; BudgetsPage `confirm()` → ConfirmDialog. 5 new regression tests. |
| Phase 2 | ✅ shipped | FY-versioned rules registry (FY23-24, FY24-25, FY25-26 — source-cited); old vs new regime calculator with 87A/surcharge/cess/Sec 24(b)/equity STCG-LTCG; deductions engine + HRA + utilization tracker + what-if optimizer; ITR-1/2/3/4 recommender; 5 new `/api/v1/tax/*` endpoints; web RegimeComparator widget on TaxPage. 47 unit + 7 API + 2 component tests. |
| Phase 3 | 🟡 partial | AIS/26AS/Form-16 ↔ ledger reconciliation engines + `GET /api/v1/tax/reconciliation/{fy}` wire-up endpoint shipped (16 + 5 tests). Connector wizard / inline-image password OCR not yet started. |
| Phase 4 | ⏳ pending | 12 new doc parsers; review workspace v2. |
| Phase 5 | ⏳ pending | LLM triad + eval harness + tax-rule RAG. |
| Phase 6 | 🟡 partial | Global FY selector (FYContext + FYSelector widget in header + sidebar; 5 tests); ConfirmDialog rollout (BudgetsPage); mobile Alert→toast sweep (6 screens migrated). Animation library + iOS assets still pending. |
| Phase 7 | 🟡 in-progress | LLM eval harness + Playwright/Maestro pending. Backend unit/API coverage grew by 80 tests this PR. |
| Phase 8 | ⏳ pending | Router decomposition, bundle splitting, pgvector tuning. |
| Phase 9 | ⏳ pending | DPDP consent, audit log, data export/delete, self-host bootstrap. |
| Phase 10 | ⏳ pending | Long-tail features. |

**Latest CI on branch `phase1/correctness-and-tax-foundation`:** all jobs green at commit `fe613cb`.
**Latest test totals:** backend 361 pass / 42 skipped (E2E gated); frontend vitest 30 pass; mobile jest 6 pass; tsc clean.

**Status of this plan:** Phases 0-2 fully complete. Phases 3 + 6 + 7 partially shipped. Continuing through long-tail items in subsequent PRs.
