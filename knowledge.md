# HisabClub — Complete Project Knowledge Transfer

## What is HisabClub?

A **privacy-first, self-hosted Indian personal finance ledger**. Users upload bank/credit-card statements and tax-supporting documents (`.pdf`, `.xlsx`, `.xls`, `.csv`), optionally sync Android SMS transaction alerts, and the app merges all sources into a unified ledger with automatic categorization, spending insights, bill tracking, and tax/audit assessment.

**Core differentiators:**
- Indian bank statement expertise (HDFC, Axis, SBI parsers)
- Password-protected PDF handling (pikepdf decryption)
- Mixed-format local document intake for tax/demat artifacts (`pdf/xlsx/xls/csv`)
- Cross-source reconciliation (statement + SMS dedup)
- Self-hosted (all data stays on your server)
- Deterministic core logic, LLM only as feature-flagged fallback
- Privacy-first: OTPs and personal messages never leave the device

---

## Current Supported Runtime

This is the verified development/runtime topology as of 2026-04-06:

- **Backend** runs on the host at `http://localhost:8356`
- **Web frontend** is built to `frontend/dist` and served by the backend at `/`
- **PostgreSQL** and **Redis** run in Docker
- **Primary local LLM** now runs outside this repo from `/home/ankit/Documents/local-llm` at `http://localhost:8096/v1`
  - active model: `Qwen3-VL-8B-Instruct-Q4_K_M.gguf`
- **Legacy text endpoint on `:8472` is no longer the active application path**
- **Optional local OCR/vision endpoint** can run outside this repo from `/home/ankit/Documents/local-llm` at `http://localhost:8095/v1`
- **Optional dedicated vision extraction endpoint** can be configured separately for page-image parsing (for example `Qwen3-VL-8B` served from a local OpenAI-compatible `/v1` endpoint)
- **Local document knowledge** is stored in PostgreSQL and populated from uploads, folder intake, and backfill
- **Expo Metro** runs on the host at `http://localhost:8081` for mobile debug
- **Physical Android devices** connect through `adb reverse` for `8356` and `8081`
- **Permanent dev API domain** defaults to `https://hisabclub-dev-api.ankit-tech.store/api/v1`
- **Permanent dev web domain** defaults to `https://hisabclub-dev-web.ankit-tech.store`
- **Recommended public tunnel target for both API and web** is the host backend on `http://192.168.1.69:8356`
- **Vite on `:5276`** is optional local-only hot reload and should not be the stable public web origin

The Docker `api` service is not the primary supported path right now. The supported path is host backend + Docker db/redis + host LLM.

---

## Architecture Overview

```
                        ┌─────────────────────┐
                        │   Android App (APK)  │
                        │   React Native/Expo  │
                        │   + SMS Reader       │
                        └──────────┬──────────┘
                                   │
┌─────────────────┐    ┌──────────▼──────────┐    ┌─────────────────┐
│   Web Frontend  │───▶│   FastAPI Backend    │◀───│ Shared Local LLM│
│   React + Vite  │    │   Python 3.10       │    │  llama.cpp      │
│   Built to dist │    │   Host runtime      │    │  Host runtime    │
│   Served at /   │    │   Port 8356         │    │  Port 8472       │
│   via backend   │    │   Serves API + SPA  │    └─────────────────┘
└─────────────────┘    └──────────┬──────────┘
                                   │
                        ┌─────────┴─────────┐
                        │                   │
                   ┌────▼────┐        ┌────▼────┐
                   │ Postgres│        │  Redis  │
                   │ Port 6543│       │Port 6769│
                   │ (Docker)│        │(Docker) │
                   └─────────┘        └─────────┘
```

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| **Backend** | Python + FastAPI | 3.10 / 0.115+ |
| **Database** | PostgreSQL (Docker) | 16-alpine |
| **Cache** | Redis (Docker) | 7-alpine |
| **ORM** | SQLAlchemy (async) + Alembic | 2.0 |
| **PDF Parsing** | pikepdf (decrypt) + pdfplumber (extract) | 9.4+ / 0.11+ |
| **Auth** | JWT (python-jose) + Argon2 | HS256 |
| **Web Frontend** | React + TypeScript + Vite + TailwindCSS | 19 / 8.0 / 4.2 |
| **Charts** | Recharts | 3.8 |
| **Mobile** | React Native + Expo + React Navigation | 0.83 / 55 / 7 |
| **Mobile UI** | React Native Paper (Material Design 3) | 5.15 |
| **Mobile State** | TanStack React Query | 5.94 |
| **SMS Reader** | Custom Kotlin native module (ContentResolver) | - |
| **LLM** | llama.cpp `Qwen3-VL-8B-Instruct` on `:8096` | - |
| **Containers** | Docker Compose | - |

---

## Recent Parsing / Retrieval Changes

- Upload API now accepts `pdf/xlsx/xls/csv`:
  - statement parsing remains PDF-first
  - spreadsheet/CSV uploads are stored as `document_artifacts` and routed through tax/demat classification
- Parser now supports selective OCR fallback for scanned or low-signal PDFs:
  - native text extraction runs first
  - only empty/low-signal pages are rendered and sent to a local OpenAI-compatible vision endpoint
  - OCR output is merged back into the page stream before parser/LLM extraction
- Upload and folder-import flows now ingest decrypted PDF text into `document_knowledge_chunks`.
- Statement parsing builds same-user context from prior chunks and prior parsed statements before LLM classification or fallback extraction.
- Local LLM access is now routed by task rather than hardwired:
  - text extraction/classification/review use the shared text route
  - OCR transcription uses the OCR route
  - optional page-image statement extraction can use a separate vision route
- Statement extraction now runs a post-parse validation pass that drops duplicate rows, invalid amounts/directions, and implausible out-of-range dates before persistence/promotion.
- Backend now supports optional vision-first fallback extraction from rendered PDF pages:
  - disabled by default
  - intended for dedicated local models such as `Qwen3-VL-8B`
  - invoked before text-only fallback when enabled for hard/low-signal statements
- Backend now also supports **primary** vision-led PDF-to-JSON extraction:
  - enabled only when `LLM_VISION_STATEMENT_PRIMARY=true`
  - rendered statement pages are sent to the dedicated local vision route before template parsing
  - template/text extraction remain as fallback for resilience
- Vision extraction confidence defaults were raised for rows where the model omits explicit `confidence`, preventing good rows from being quarantined by default.
- Folder import now commits incrementally:
  - artifacts and parsed statements become visible during long imports
  - request-scoped tenant context is re-applied after commit to satisfy RLS
  - knowledge ingestion now commits before the expensive statement parse begins, reducing long `idle in transaction` windows
- Real-directory validation against `/home/ankit/Documents/FY24-25-Ankit-details` now confirms successful `Qwen3-VL` parsing for:
  - `0206-statement.pdf` -> `BOB savings`, `13` transactions
  - `ANKIT-HDFC-CC-STATEMENT.pdf` -> `HDFC credit_card`, `66` transactions
  - `9719-statement.pdf` -> `ICICI savings`, `186` transactions
  - all three promoted cleanly with `parser_used=llm_vision_page_extract`
- PostgreSQL remains the source of truth; no NoSQL replacement is planned for the ledger/review/audit path.
- Savings/current statements now run a deterministic balance-walk check:
  - `opening_balance + credits - debits ~= closing_balance`
  - mismatches are stored in `statement.parse_errors.validation.balance_walk`
  - worker promotion gates can force such statements into `review_required`
- Bank inference now prefers statement-header matches over incidental bank names inside transaction descriptions.
- Classifier false positives were reduced:
  - short tokens like `cas` are word-boundary matched (so `cash` no longer triggers demat by mistake)
  - generic `interest` no longer auto-forces `interest_certificate` without certificate cues
- Upload review notifications now have a persistent backend feed at `GET /api/v1/upload/recent`.
- Statements can now be deleted with full local cleanup, including `raw_pdfs`, stored PDF files, and `document_knowledge_chunks`.
- Statements can now be re-reviewed through the local LLM using the stored PDF as the source of truth.
- Existing PDFs can be reindexed into the local knowledge store with `make backfill-knowledge`.
- Canonical promotion now runs atomically inside a DB savepoint so partial failures cannot leave orphaned ledger rows.
- Statement ingestion now computes semantic statement fingerprints and blocks accidental duplicate statement insertion unless reprocess is explicitly allowed.
- File dedup is content-hash based (`SHA-256`) per user:
  - same-content files with different names are treated as duplicates
  - duplicate response now includes the matched prior file name
- Transaction dedup now has a deterministic fingerprint path (`user + account + date + abs(amount) + normalized description prefix`) in addition to fuzzy matching.
- Transaction dedup is now account-aware in fingerprint, exact-reference, and fuzzy amount/date matching paths.
- LLM sanitization now preserves operational transaction references such as `UPI/UTR/IMPS/NEFT/RTGS` IDs while still masking explicit account/card identifiers.
- Credit-card integrity review now excludes quarantined rows and uses structured JSON parsing instead of free-form parsing.
- OCR backend path is code-complete but not operationally active until OCR model artifacts are added under `/home/ankit/Documents/local-llm/models`.
- Merchant normalization now caches merchant patterns in-process during promotion to reduce repeated full-table scans.
- Transfer/card-payment pairing now persists auditable matches in `transfer_matches`.
- Gmail OAuth credentials are now encrypted at rest and remain backward-compatible with previously stored plaintext rows.
- Tax & Audit web page now uses Financial Year selection:
  - Running FY + previous 5 FYs
  - auto-refresh on FY change with optional manual refresh buttons

## 2026-03-30 Architecture-Update Implementation

- Statement ingestion is now **durable and queue-first**:
  - `upload/pdf` creates `raw_pdfs` + `extraction_jobs`, then returns `reviewing`
  - worker loop claims jobs from PostgreSQL with retry/backoff and DLQ state
  - upload status/recent endpoints now surface job state even before statement materialization
- Added operational APIs for ingestion reliability:
  - `GET /api/v1/upload/jobs/dlq`
  - `POST /api/v1/upload/jobs/{job_id}/requeue`
  - `GET /api/v1/upload/parser-health`
- Added institution password-pattern registry and resolver:
  - model: `institution_password_patterns`
  - APIs: list/upsert/delete under `/api/v1/gmail/password-patterns`
  - used by manual upload, Gmail sync, and statement re-review for encrypted PDFs
- Gmail sync now enqueues parse jobs instead of parsing attachments inline.
- Parser observability now updates `institution_parser_support` success/failure counters from worker outcomes.
- Added DB-level tenant isolation migrations:
  - RLS policies + FORCE RLS on user-scoped tables
  - request context via `app.current_user_id`
  - worker bypass via `app.worker_mode=1`
- Added runtime DB-role switch (`SET ROLE hisabclub_rls`) in API/worker sessions so RLS remains effective even if the bootstrap user has elevated privileges.

## 2026-03-30 Phase 2 Implementation (Architecture-Update)

- LLM orchestration upgraded for long-statement reliability:
  - iterative chunk extraction in `app/engines/llm/parse_fallback.py`
  - prompt templates and few-shot bank examples in `app/engines/llm/prompts.py`
  - deterministic model-routing hooks in `app/engines/llm/router.py`
  - JSON-structured response support in `LLMClient.chat_json()`
- Added extraction quality controls and partial promotion:
  - `PROMOTION_CONFIDENCE_THRESHOLD` now gates canonical promotion
  - low-confidence rows are stored as quarantined `parsed_transactions`
  - `review_tasks` table added with APIs:
    - `GET /api/v1/reviews/tasks`
    - `POST /api/v1/reviews/tasks/{task_id}/resolve`
  - statement-level quality metrics added:
    - `expected_row_count`, `extracted_row_count`, `promoted_row_count`, `quarantined_row_count`, `yield_rate`
- Added yield-rate observability:
  - parser pre-estimate via `estimate_expected_transaction_rows()`
  - parser-health now reports expected/extracted rows and yield-rate per bank/account type
- Added UPI failed-payment reconciliation:
  - engine: `app/engines/ledger/upi_reconciliation.py`
  - API: `POST /api/v1/transactions/reconcile-upi-failures`
  - auto-run after statement parse jobs
- Added queue fairness and storage tiering:
  - per-user fair job selection in `claim_next_job()` (prevents one-user starvation)
  - hot→cold PDF movement in `app/engines/storage/tiering.py`
  - `raw_pdfs` now tracks `storage_tier` and `cold_storage_path`
- Migration `f9a0b1c2d3e4` applied successfully and is the current DB head.

## 2026-03-30 Remaining Gap Closure (Architecture-Update Completion)

- Added **cross-page table stitching path** via `extract_stitched_table_rows()` and wired it into statement parsing before LLM fallback.
- Added **tier-2 extraction path** in `llm_parse_statement()`:
  - deterministic table rows
  - LLM column mapping only
  - deterministic row-to-transaction mapping
  - fallback to iterative full extraction if mapping is insufficient
- Added **post-parse multi-gate escalation** in worker:
  - quarantine gate
  - yield-rate gate (`MIN_YIELD_RATE_FOR_AUTO_PROMOTION`)
  - optional credit-card integrity gate (`REQUIRE_CC_INTEGRITY_OK_FOR_AUTO_PROMOTION`)
- Added local **POC/eval scripts** under `scripts/`:
  - `poc_table_stitch_eval.py`
  - `poc_llm_column_mapping_eval.py`
  - `poc_ocr_compare.py`
- Verified the POC scripts execute locally with `backend/.venv/bin/python ...` and report JSON output.

## Directory Structure

```
<repo-root>/
│
├── backend/                           # Python FastAPI backend
│   ├── pyproject.toml                 # Dependencies (setuptools, pip install -e ".[dev]")
│   ├── alembic.ini                    # Alembic config
│   ├── alembic/
│   │   ├── env.py                     # Migration env (imports ALL models)
│   │   ├── script.py.mako            # Migration template
│   │   └── versions/                  # Migration files (4 migrations applied)
│   │       ├── 0fc6f5ad6d91_initial_schema.py
│   │       ├── dd80917cce50_add_raw_sms_table.py
│   │       ├── 70380c4c415c_add_insights_tables.py
│   │       └── <connected_accounts migration>.py
│   ├── .venv/                         # Python virtualenv (Python 3.10)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory + SPA serving
│   │   ├── config.py                  # Pydantic Settings (reads ../.env)
│   │   ├── database.py                # Async SQLAlchemy engine + session
│   │   ├── dependencies.py            # DI: DbSession, CurrentUser (JWT auth)
│   │   │
│   │   ├── models/                    # SQLAlchemy ORM (19 tables)
│   │   │   ├── base.py               # Base, TimestampMixin, UUIDPrimaryKeyMixin
│   │   │   ├── user.py               # Users (email, password_hash, first_name, dob)
│   │   │   ├── raw_pdf.py            # Uploaded PDFs (hash dedup, storage_path)
│   │   │   ├── raw_sms.py            # Synced SMS (sms_hash dedup)
│   │   │   ├── statement.py          # Parsed statement metadata
│   │   │   ├── parsed_transaction.py  # Per-source extracted transactions
│   │   │   ├── canonical_transaction.py # Unified ledger (THE truth)
│   │   │   ├── transaction_source.py  # Links canonical ↔ parsed (dedup lineage)
│   │   │   ├── category.py           # Hierarchical categories (73 seeded)
│   │   │   ├── merchant.py           # Merchant + MerchantPattern (48+90 seeded)
│   │   │   ├── user_override.py      # User corrections audit log + UserMerchantRule
│   │   │   ├── connected_account.py   # Gmail OAuth connections
│   │   │   ├── budget.py             # Budget per category
│   │   │   ├── bill.py               # CC bill tracking (auto-created from statements)
│   │   │   ├── document_knowledge_chunk.py # Local per-user PDF chunk memory for retrieval
│   │   │   ├── insights.py           # MonthlySummary + RecurringPattern
│   │   │   └── __init__.py           # Exports ALL models (MUST be updated when adding models)
│   │   │
│   │   ├── schemas/                   # Pydantic request/response
│   │   │   ├── auth.py, statement.py, transaction.py, upload.py
│   │   │   ├── sms.py, budget.py, bill.py, insights.py
│   │   │
│   │   ├── api/v1/                    # FastAPI routers
│   │   │   ├── router.py             # Aggregates ALL routers (MUST update when adding)
│   │   │   ├── auth.py               # POST /setup, /login, /forgot-password, /reset-password, /change-password, GET /me
│   │   │   ├── upload.py             # POST /pdf, GET /recent, GET /{pdf_id}/status
│   │   │   ├── statements.py         # GET list + detail
│   │   │   ├── transactions.py       # GET list + detail, PATCH update, GET sources
│   │   │   ├── categories.py         # GET list
│   │   │   ├── merchants.py          # GET list with search
│   │   │   ├── sms.py                # POST /batch (bulk SMS import)
│   │   │   ├── insights.py           # GET monthly-summary, trends, recurring
│   │   │   ├── budgets.py            # CRUD budgets with spent calculation
│   │   │   ├── bills.py              # CRUD bills (status: upcoming/unpaid/paid/all)
│   │   │   ├── export.py             # GET /csv (StreamingResponse)
│   │   │   ├── gmail.py              # OAuth connect, callback, sync, allowlist
│   │   │   └── imports.py            # Folder-intake + artifact listing/download
│   │   │
│   │   ├── engines/                   # Core business logic
│   │   │   ├── parser/               # Statement parsing engine
│   │   │   │   ├── base.py           # StatementParser ABC, registry, parse_statement() orchestrator
│   │   │   │   │                     # Includes LLM fallback when template returns 0 txns
│   │   │   │   ├── pdf_utils.py      # pikepdf decrypt + pdfplumber text extraction
│   │   │   │   ├── amount_utils.py   # parse_indian_amount() handles C prefix, Rs., INR, ₹
│   │   │   │   │                     # parse_indian_date() handles DD/MM/YYYY, DD-MMM-YYYY etc.
│   │   │   │   └── templates/        # 6 bank-specific parsers
│   │   │   │       ├── hdfc_cc.py    # HDFC CC (handles C prefix amounts, +/Cr credits, DATE|TIME)
│   │   │   │       ├── hdfc_savings.py # HDFC Savings (3-amt, 2-amt, labelled patterns)
│   │   │   │       ├── axis_cc.py
│   │   │   │       ├── axis_savings.py
│   │   │   │       ├── sbi_cc.py
│   │   │   │       └── sbi_savings.py
│   │   │   │
│   │   │   ├── ledger/
│   │   │   │   ├── merger.py          # promote_to_canonical() with dedup integration
│   │   │   │   ├── dedup.py           # 3-tier dedup: exact ref → fuzzy amount+date → window
│   │   │   │   └── merchant_normalizer.py # Pattern-based merchant → category matching
│   │   │   │
│   │   │   ├── insights/
│   │   │   │   ├── monthly_summary.py  # Compute income/expense/category breakdown
│   │   │   │   ├── recurring_detector.py # Detect subscriptions (monthly/quarterly/yearly)
│   │   │   │   ├── trend_analyzer.py   # Multi-month spending trends
│   │   │   │   └── bill_tracker.py     # Auto-create bills from parsed statements
│   │   │   │
│   │   │   ├── llm/                   # LLM fallback (feature-flagged)
│   │   │   │   ├── client.py          # OpenAI-compatible HTTP client (httpx)
│   │   │   │   ├── knowledge.py       # Customer-scoped retrieval over stored PDF chunks
│   │   │   │   ├── sanitizer.py       # Strip PII before LLM (cards, names, PAN, Aadhaar)
│   │   │   │   ├── parse_fallback.py  # LLM parses unknown PDF layouts → ExtractedStatement
│   │   │   │   ├── statement_classifier.py # LLM bank/account-type classification for ambiguous PDFs
│   │   │   │   ├── merchant_cleanup.py # LLM normalizes merchant names
│   │   │   │   └── categorizer.py     # LLM suggests transaction categories
│   │   │   │
│   │   │   ├── gmail/
│   │   │   │   └── service.py         # GmailService: OAuth, fetch PDFs, sync
│   │   │   │
│   │   │   └── policy/               # (Stubs for fraud/anomaly detection)
│   │   │
│   │   ├── seed/                      # Database seeding
│   │   │   ├── categories.py          # 16 parent + 57 subcategories
│   │   │   ├── merchants.py           # 48 merchants + 90 patterns (Swiggy, Amazon, Uber, etc.)
│   │   │   └── run.py                 # Seed runner (python -m app.seed.run)
│   │   │
│   │   └── tasks/
│   │       └── backfill_document_knowledge.py # Reindex existing PDFs into local retrieval memory
│   │
│   └── tests/                         # Active pytest suite
│       ├── test_api/                  # Upload + insights API coverage
│       ├── test_insights/             # Reconciliation, integrity, tax compliance
│       ├── test_intake/               # Document classification
│       ├── test_ledger/               # Nature classification
│       ├── test_llm/                  # LLM client payload behavior
│       └── test_parser/               # Credit-card parser coverage + hint inference
│
├── frontend/                          # React + Vite + TailwindCSS web app
│   ├── package.json
│   ├── vite.config.ts                 # Optional local-only hot reload on :5276, proxy /api → :8356
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.tsx                   # Entry point
│   │   ├── index.css                  # Tailwind import
│   │   ├── App.tsx                    # Routes: /, /upload, /transactions, /statements,
│   │   │                              #   /insights, /budgets, /bills, /tax, /gmail, /imports
│   │   ├── api/
│   │   │   └── client.ts             # ApiClient class + all type interfaces
│   │   │                              # getBills/getBudgets unwrap {items} from response
│   │   ├── components/
│   │   │   └── Layout.tsx            # Sidebar nav + main content + Export CSV button
│   │   └── pages/
│   │       ├── LoginPage.tsx         # Sign in + setup + forgot-password request
│   │       ├── ResetPasswordPage.tsx # Public one-time token reset
│   │       ├── AccountPage.tsx       # Authenticated profile + change-password
│   │       ├── DashboardPage.tsx      # Summary cards + PieChart + BarChart + bills + recent txns
│   │       ├── UploadPage.tsx         # Drag-drop PDF + password + bank hint
│   │       ├── TransactionsPage.tsx   # Filterable paginated table
│   │       ├── StatementsPage.tsx     # Statement cards
│   │       ├── InsightsPage.tsx       # Full analytics: PieChart, BarChart, recurring, top merchants
│   │       ├── BudgetsPage.tsx        # Budget progress bars + create/delete
│   │       ├── BillsPage.tsx          # Upcoming/Paid tabs + mark paid + due badges
│   │       ├── TaxPage.tsx            # Tax-compliance and transfer reconciliation
│   │       ├── ImportsPage.tsx        # Folder intake status + artifact viewer
│   │       └── GmailPage.tsx          # Connect Gmail + allowlist + sync
│   └── dist/                          # Built static files (served by backend)
│
├── mobile/                            # React Native + Expo Android app
│   ├── app.json                       # Expo config: package=com.hisabclub.app, READ_SMS permission
│   ├── eas.json                       # EAS Build profiles (APK output)
│   ├── package.json
│   ├── App.tsx                        # Re-exports src/App.tsx
│   ├── src/
│   │   ├── App.tsx                    # QueryClientProvider + PaperProvider + AuthProvider + Navigation
│   │   ├── api/
│   │   │   ├── client.ts             # API functions (uses SecureStore, configurable server URL)
│   │   │   └── types.ts              # All TypeScript interfaces
│   │   ├── auth/
│   │   │   └── AuthContext.tsx        # Auth state context + useAuth hook
│   │   ├── navigation/
│   │   │   ├── types.ts              # Navigation param types
│   │   │   ├── RootNavigator.tsx      # Auth check → AuthStack or MainTabs + stack screens
│   │   │   ├── AuthStack.tsx          # LoginScreen
│   │   │   └── MainTabs.tsx           # Bottom tabs: Home, Transactions, Insights, Settings
│   │   ├── screens/                   # 11 screens
│   │   │   ├── LoginScreen.tsx        # Server URL + email/password + forgot-password request
│   │   │   ├── DashboardScreen.tsx    # Summary + bills + categories + quick actions + recent txns
│   │   │   ├── TransactionsScreen.tsx # Infinite scroll + search + filter
│   │   │   ├── TransactionDetailScreen.tsx # View + edit category/notes
│   │   │   ├── UploadScreen.tsx       # Document picker + CC/Bank type + password hint
│   │   │   ├── StatementsScreen.tsx
│   │   │   ├── InsightsScreen.tsx     # Category bars + recurring + top merchants
│   │   │   ├── BudgetsScreen.tsx      # Progress bars + FAB create dialog
│   │   │   ├── BillsScreen.tsx        # Segmented filter + due badges + mark paid
│   │   │   ├── SettingsScreen.tsx     # Theme, server URL, password change, SMS sync, logout
│   │   │   └── SmsSyncScreen.tsx      # Permission request, Sync Now, Preview, history
│   │   ├── sms/                       # On-device SMS processing (privacy-first)
│   │   │   ├── bankPatterns.ts        # 30+ sender IDs, regex patterns, amount/date extraction
│   │   │   ├── SmsFilterer.ts         # Classification + spam scoring (requires account reference)
│   │   │   ├── SmsParser.ts           # Extract amount, direction, account, UPI ref
│   │   │   ├── SmsSyncService.ts      # Orchestrator: read → filter → parse → POST /sms/batch
│   │   │   ├── SmsBridge.ts           # Platform gate (PermissionsAndroid for popup)
│   │   │   └── types.ts
│   │   ├── theme/
│   │   │   └── AppThemeProvider.tsx   # Light/dark/auto theme state for Paper + navigation
│   │   ├── modules/
│   │   │   └── sms-reader/
│   │   │       ├── index.ts           # JS interface to native module
│   │   │       └── android/
│   │   │           ├── SmsReaderModule.kt   # Kotlin: ContentResolver query content://sms/inbox
│   │   │           └── SmsReaderPackage.kt  # React Native package registration
│   │   ├── components/
│   │   │   ├── TransactionRow.tsx, AmountText.tsx, EmptyState.tsx
│   │   ├── hooks/                     # (stubs)
│   │   └── utils/
│   │       ├── constants.ts           # DEFAULT_API_URL, COLORS, BANKS, STORAGE_KEYS
│   │       ├── formatters.ts          # formatAmount(INR), formatDate(en-IN)
│   │       └── storage.ts             # SecureStore (token) + AsyncStorage (serverUrl, syncTimestamp)
│   └── android/                       # Generated by expo prebuild (regenerated on prebuild!)
│       └── app/src/main/java/com/hisabclub/app/
│           ├── MainApplication.kt     # Must re-add SmsReaderPackage after each prebuild
│           └── smsreader/             # Must re-copy after each prebuild
│               ├── SmsReaderModule.kt
│               └── SmsReaderPackage.kt
│
├── uploads/                           # User-uploaded PDFs (gitignored)
│
├── infra/docker/                      # Infrastructure templates (stubs)
│
├── docker-compose.yml                 # PostgreSQL 16 (:6543) + Redis 7 (:6769)
├── Makefile                           # Dev commands (uses backend/.venv/bin)
├── .env                               # Active config (LLM_ENABLED=true, ports 6543/6769)
├── .env.example                       # Template
├── .gitignore                         # Standard Python/Node/Docker ignores + uploads/
└── knowledge.md                       # THIS FILE
```

---

## Database Schema (18 tables, PostgreSQL 16)

### Three-Tier Transaction Pipeline
```
Raw Sources → Parsed Transactions → Canonical Transactions
(raw_pdfs)     (parsed_transactions)  (canonical_transactions)
(raw_sms)                              ↕ (transaction_sources = dedup lineage)
```

### Key Tables

| Table | Purpose | Key Fields |
|---|---|---|
| **users** | Accounts | email, password_hash (argon2), first_name, date_of_birth |
| **raw_pdfs** | Uploaded PDFs | file_hash_sha256 (dedup), storage_path, is_password_protected |
| **raw_sms** | Synced SMS | sms_hash (dedup), sender_address, body, classification, confidence |
| **statements** | Parsed statement metadata | bank_name, account_type, period, due_date, amounts, parser_used, parse_status |
| **parsed_transactions** | Per-source extractions | source_type (statement/sms), amount, direction, confidence, extraction_method |
| **canonical_transactions** | THE unified ledger | merchant_raw/normalized, category_id, bank_name, is_recurring, is_anomalous, tags |
| **transaction_sources** | Dedup lineage | canonical_txn_id ↔ parsed_txn_id, match_confidence, match_method |
| **categories** | Hierarchical (73 seeded) | name, parent_id, icon, color, is_system |
| **merchants** | Normalized merchants (48) | name_normalized, display_name, default_category_id |
| **merchant_patterns** | Matching rules (90) | pattern, pattern_type (contains/regex/exact), priority |
| **user_overrides** | Correction audit log | field_name, old_value, new_value |
| **user_merchant_rules** | User-taught mappings | pattern → merchant_id + category_id |
| **connected_accounts** | Gmail OAuth | credentials_enc, sender_allowlist (JSONB) |
| **budgets** | Per-category budgets | category_id, amount_limit, period (monthly/yearly) |
| **bills** | CC bill tracking | bank_name, due_date, total_due, min_due, is_paid |
| **monthly_summaries** | Precomputed analytics | year_month, income, expense, category_breakdown (JSONB) |
| **recurring_patterns** | Detected subscriptions | description_pattern, typical_amount, frequency, next_expected |

---

## API Endpoints

### Auth (`/api/v1/auth`)
| Method | Path | Description |
|---|---|---|
| POST | `/setup` | First-time user creation (blocks if user exists) |
| POST | `/login` | Returns JWT access + refresh tokens |
| POST | `/forgot-password` | Issues one-time password reset instructions |
| POST | `/reset-password` | Consumes a reset token and sets a new password |
| POST | `/change-password` | Changes password for the authenticated user |
| GET | `/me` | Current user profile |

### Upload (`/api/v1/upload`)
| Method | Path | Description |
|---|---|---|
| POST | `/pdf` | Upload PDF (multipart: file, password?, bank_hint?) |
| GET | `/{pdf_id}/status` | Check parse status |

### Statements (`/api/v1/statements`)
| Method | Path | Description |
|---|---|---|
| GET | `/` | List statements (filter: bank, account_type) |
| GET | `/{id}` | Statement detail |
| GET | `/{id}/pdf` | Stream the source PDF for browser viewing |

### Transactions (`/api/v1/transactions`)
| Method | Path | Description |
|---|---|---|
| GET | `/` | List (filters: from, to, bank, direction, category_id, min/max_amount, search, page, per_page) |
| GET | `/{id}` | Detail with category name |
| PATCH | `/{id}` | Update (category_id, merchant_id, notes, tags, is_excluded) — creates override audit |
| GET | `/{id}/sources` | Source lineage (which statement/SMS contributed) |
| POST | `/reclassify-transfer-payments` | Re-run transfer and credit-card payment reclassification |

### Categories (`/api/v1/categories`) — GET list
### Merchants (`/api/v1/merchants`) — GET list with search

### SMS (`/api/v1/sms`)
| POST | `/batch` | Bulk import parsed SMS ({device_id, items[]}) with sms_hash dedup |

### Insights (`/api/v1/insights`)
| GET | `/monthly-summary?month=` | Income/expense/net + category breakdown + top merchants + vs_last_month |
| GET | `/trends?months=6` | Multi-month trend data for charts |
| GET | `/recurring` | Detected recurring transactions |
| GET | `/reconciliation` | Match internal transfers across accounts/statements |
| GET | `/tax-compliance` | New-regime tax estimate + document coverage + action items |
| POST | `/recompute?months=12` | Force recompute all summaries |

### Budgets (`/api/v1/budgets`)
| GET | `/` | List with real-time spent_amount computed from canonical_transactions |
| POST | `/` | Create {category_id, amount_limit, period} |
| PATCH | `/{id}` | Update amount or is_active |
| DELETE | `/{id}` | Soft delete (is_active=false) |

### Bills (`/api/v1/bills`)
| GET | `/?status=upcoming\|unpaid\|paid\|all` | List ordered by due_date |
| POST | `/` | Create manually |
| PATCH | `/{id}` | Mark paid {is_paid, paid_amount, paid_date} |

### Export (`/api/v1/export`)
| GET | `/csv?from=&to=&bank=` | StreamingResponse CSV download |

### Gmail (`/api/v1/gmail`)
| POST | `/connect` | Returns {auth_url} for OAuth |
| GET | `/callback` | OAuth callback handler |
| POST | `/sync` | Trigger manual sync |
| GET | `/allowlist` | Get sender allowlist |
| PUT | `/allowlist` | Update allowlist |

### Imports (`/api/v1/imports`)
| Method | Path | Description |
|---|---|---|
| POST | `/folder` | Scan a local document directory and import supported files |
| GET | `/artifacts` | List discovered artifacts and parse status |
| GET | `/artifacts/{id}/file` | Stream original artifact for browser viewing |
| GET | `/parser-support-queue` | Group unresolved bank-statement artifacts by support gap |
| POST | `/reclassify-nature` | Recompute transaction nature labels from ledger data |

### Health
| GET | `/health` | Returns {status: "ok", app: "HisabClub"} |

---

## Statement Parsers (6 registered)

| Parser ID | Bank | Type | Key Format Notes |
|---|---|---|---|
| `hdfc_cc_v1` | HDFC | credit_card | `C` prefix for amounts (₹→C artifact), `+` for credits, `DD/MM/YYYY\| HH:MM` dates, `l` PI indicator at end |
| `hdfc_savings_v1` | HDFC | savings | 3-amount (withdrawal/deposit/balance), 2-amount, labelled (Cr/Dr) patterns |
| `axis_cc_v1` | AXIS | credit_card | Standard DD/MM/YYYY + Amount + Cr/Dr |
| `axis_savings_v1` | AXIS | savings | Same multi-pattern approach as HDFC savings |
| `sbi_cc_v1` | SBI | credit_card | SBI Card format |
| `sbi_savings_v1` | SBI | savings | Handles 2-date format (Txn Date + Value Date) |

### Parser Pipeline
```
PDF bytes + password → pikepdf decrypt → pdfplumber extract text → detect parser →
  template parse → [if 0 txns + LLM enabled → LLM fallback] → save Statement →
  for each txn: create ParsedTransaction → promote_to_canonical (with dedup) →
  auto-create Bill if due_date present
```

### Adding a New Bank Parser
1. Create `backend/app/engines/parser/templates/<bank>_<type>.py`
2. Implement `StatementParser` ABC: `parser_id`, `bank_name`, `account_type`, `detect()`, `parse()`
3. Call `register_parser(YourParser())` at module level
4. Add import to `_ensure_parsers_loaded()` in `backend/app/engines/parser/base.py`

---

## SMS Processing (On-Device, Android Only)

### Pipeline (privacy-first — raw SMS never leaves device)
```
Native Module reads inbox → filter by known sender IDs → classify →
  [OTPs/promos/spam discarded] → parse transaction details →
  POST /api/v1/sms/batch (only parsed data, not raw SMS)
```

### Key Design Decisions
- **Account reference required**: SMS must contain `a/c XX1234` or similar to be classified as transaction (prevents promo spam like "Get Rs.6,000 Cashback")
- **Sender ID format**: Handles `XX-BANKID` and `XX-BANKID-X` (e.g., `AD-ICICIT-S` → ICICI)
- **30+ known sender IDs**: HDFC, ICICI, AXIS, SBI, Kotak, PNB, IndusInd, Yes, IDFC, + wallets (Paytm, PhonePe)
- **PermissionsAndroid.request()** for system permission dialog (not native module)

### After `expo prebuild`
The `android/` directory is regenerated. You MUST:
1. Re-copy Kotlin files: `cp src/modules/sms-reader/android/*.kt android/app/src/main/java/com/hisabclub/app/smsreader/`
2. Re-add to MainApplication.kt: `import com.hisabclub.app.smsreader.SmsReaderPackage` and `add(SmsReaderPackage())` in packages list

---

## LLM Configuration

### Shared Local LLM Runtime
```bash
cd /home/ankit/Documents/local-llm
./llama-turbo-cuda.sh start
```

### Model Details
- **File**: `/home/ankit/Documents/local-llm/models/unsloth-Qwen3.5-27B-GGUF/Qwen3.5-27B-Q3_K_M.gguf`
- **Model**: Qwen3.5-27B, Q3_K_M quantization
- **GPU**: NVIDIA RTX A5000 (24GB VRAM) — all 65 layers offloaded
- **Performance**: ~27 tokens/sec
- **API**: OpenAI-compatible at `http://localhost:8472/v1`
- **Ownership**: model runtime is managed in `/home/ankit/Documents/local-llm`, not in this repo

### LLM Usage in App
- **Feature-flagged**: `LLM_ENABLED=true` in `.env`
- **Fallback for 0-transaction parsing**: When template parser returns 0 transactions
- **Merchant normalization**: Clean up messy raw merchant descriptions
- **Category suggestion**: Pick best category from list
- **PII sanitized** before any LLM call (cards, names, PAN, Aadhaar, OTPs stripped)
- **Qwen local runtime**: requests set `chat_template_kwargs.enable_thinking=false` so local llama.cpp returns usable `message.content`

---

## Global System Packages Installed

| Package | Version | Location |
|---|---|---|
| **JDK 17** | 17.0.18 | `/usr/lib/jvm/java-17-openjdk-amd64` |
| **Android SDK** | cmdline-tools + platform 34 + build-tools 34.0.0 | `~/android-sdk` |
| **NVIDIA Container Toolkit** | 1.19.0 | System-wide (for Docker GPU) |
| **llama-server** | From llama.cpp | `/usr/local/bin/llama-server` |
| **ADB** | System | `/usr/bin/adb` |
| **Node.js** | v22.22.1 | via nvm |
| **Python** | 3.10.12 | `/usr/bin/python3` |

### Environment Variables for Android Builds
```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_HOME=~/android-sdk
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
```

---

## Build & Deploy Commands

### Recommended local workflow
```bash
make setup
make local-stack
make local-check
```

`make local-stack` is the supported entrypoint. It starts Docker db/redis, ensures the shared local LLM is up, builds the frontend, applies migrations, seeds categories/merchants, and runs the backend on the host.

### Backend
```bash
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8356 --log-level info   # Start
.venv/bin/alembic upgrade head                                                  # Apply migrations
.venv/bin/alembic revision --autogenerate -m "description"                     # New migration
.venv/bin/python -m app.seed.run                                               # Seed categories + merchants
```

### Web Frontend
```bash
cd frontend
npm run dev           # Dev server on :5276 when needed
npm run build         # Build to dist/ (served by backend at /)
```

### Mobile APK
```bash
cd mobile
npx expo prebuild --platform android --clean   # Generate android/ (WIPES customizations!)

# Re-apply native module:
mkdir -p android/app/src/main/java/com/hisabclub/app/smsreader
cp src/modules/sms-reader/android/*.kt android/app/src/main/java/com/hisabclub/app/smsreader/
# Edit android/app/src/main/java/com/hisabclub/app/MainApplication.kt:
#   Add import: com.hisabclub.app.smsreader.SmsReaderPackage
#   Add to packages: add(SmsReaderPackage())

# Build:
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_HOME=~/android-sdk
cd android && ./gradlew assembleRelease
# APK at: android/app/build/outputs/apk/release/app-release.apk

# Install via ADB:
/usr/bin/adb push <apk-path> /data/local/tmp/hisabclub.apk
/usr/bin/adb shell pm install -r /data/local/tmp/hisabclub.apk
/usr/bin/adb shell am start -n com.hisabclub.app/.MainActivity
```

### Debug mobile against local backend
```bash
make android-install
make mobile-dev
```

This applies `adb reverse` for `8356` and `8081`, then starts Metro for the dev client.

### Docker Services
```bash
docker compose up -d                 # Start PostgreSQL + Redis
docker compose down                  # Stop
```

---

## Rules for Updating the Codebase

### Adding a New Model
1. Create file in `backend/app/models/<name>.py`
2. Add import to `backend/app/models/__init__.py` (both import and `__all__`)
3. Add import to `backend/alembic/env.py`
4. Run: `.venv/bin/alembic revision --autogenerate -m "add <name> table"`
5. Apply: `.venv/bin/alembic upgrade head`

### Adding a New API Endpoint
1. Create file in `backend/app/api/v1/<name>.py`
2. Add router import + `include_router()` to `backend/app/api/v1/router.py`
3. Add Pydantic schemas to `backend/app/schemas/<name>.py`
4. Use `CurrentUser` and `DbSession` from `app.dependencies`

### Adding a New Web Page
1. Create `frontend/src/pages/<Name>Page.tsx`
2. Add route in `frontend/src/App.tsx`
3. Add nav item in `frontend/src/components/Layout.tsx`
4. Add API methods/types to `frontend/src/api/client.ts`
5. Rebuild: `npx vite build`

### Adding a New Mobile Screen
1. Create `mobile/src/screens/<Name>Screen.tsx`
2. Add to navigation types in `mobile/src/navigation/types.ts`
3. Add to `RootNavigator.tsx` or `MainTabs.tsx`
4. Add API methods to `mobile/src/api/client.ts` and types to `types.ts`

### Important: API Response Format
- List endpoints return `{items: [...], total: N}` — frontends must unwrap `.items`
- Mobile API client functions already unwrap for `getBills()` and `getBudgets()`
- Web API client also unwraps for these

---

## Current Gaps / Operational Notes

1. **Parser coverage is still bank-template heavy** — HDFC, Axis, and SBI formats are the strongest supported paths. Kotak, BOB, ICICI, and atypical statement layouts still depend on classifier heuristics and LLM fallback, so some imports remain unresolved.
2. **Gmail OAuth is not usable until credentials are configured** — `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` are empty by default.
3. **Docker API runtime is not the recommended path** — the verified topology is host backend + Docker db/redis + host LLM.
4. **Expo prebuild still wipes native Android customizations** — after `expo prebuild --clean`, the SMS reader Kotlin files and `MainApplication.kt` integration must be restored.
5. **Expo debug loader can emit a non-fatal startup warning** — during Metro handoff on device, a dev-only loading popup warning may appear even though the app stays alive.
6. **Redis is present but lightly used** — there is no full background worker pipeline yet.
7. **Frontend bundle is large** — the production build currently reports a Vite chunk-size warning, but it builds and runs correctly.

---

## Verified State (2026-03-29)

- Backend health endpoint returns OK
- Shared local LLM responds on `:8472`
- Frontend production build succeeds
- Backend pytest suite passes: `27 passed`
- Seeded categories are available after login: `73`
- Web frontend renders through the backend-served SPA
- Android debug app installs and launches on a connected physical device

---

## What Was Built (Session History)

### Phase 1: MVP
- Project scaffolding, Docker Compose, pyproject.toml, Makefile
- All 18 database models + Alembic migrations
- FastAPI app with auth (JWT + Argon2)
- Statement parser engine with 3 CC parsers (HDFC, Axis, SBI)
- Ledger engine (promote parsed → canonical + merchant matching)
- 73 categories + 48 merchants seeded
- Web frontend: Login, Dashboard, Upload, Transactions, Statements
- All verified working with curl tests

### Phase 2: Mobile App
- Expo React Native project with full UI
- 11 screens matching web features
- Custom Kotlin SMS reader native module
- On-device SMS parsing + spam filtering
- Backend SMS batch endpoint
- APK built and installed via ADB

### Phase 3: Production Features
- **Insights engine**: monthly summaries, category breakdown, trends, recurring detection
- **Budget tracker**: per-category budgets with real-time spent calculation
- **Bill tracker**: auto-created from CC statements, due date tracking
- **CSV export**: streaming download
- **LLM integration**: client, PII sanitizer, parse fallback, merchant cleanup, categorizer
- **Gmail integration**: OAuth, sender allowlist, sync
- **Cross-source dedup**: 3-tier (exact ref → fuzzy → window)
- **Web frontend upgrade**: Insights/Budgets/Bills/Gmail pages, dashboard charts
- **Mobile upgrade**: Insights/Budgets/Bills screens, enhanced dashboard

### Phase 4: Bug Fixes
- Fixed HDFC CC parser for real Swiggy HDFC card format (C prefix, + credits, DATE|TIME)
- Fixed SMS spam filter (require account reference, handle XX-BANKID-X format)
- Fixed mobile crash on signup (empty bills/budgets response handling)
- Fixed API client getBills/getBudgets unwrapping {items} response
- Fixed bills endpoint to accept `?status=upcoming`
- Added savings account parsers (HDFC, Axis, SBI)
- Added LLM fallback when template returns 0 transactions
- Fixed web UI serving via Cloudflare tunnel (static files from backend)
- Fixed password manager autofill on LoginScreen
- Added debug text saving for PDF uploads

---

## Future Plan & Goals

### Short-term (Next Sprint)
1. **Broaden parser coverage** — Add Kotak, ICICI, BOB, and other common Indian statement formats
2. **Increase ingestion confidence** — Expand tests around folder intake, unsupported-bank routing, and LLM fallback
3. **Test SMS on real device with live messages** — Verify native module classification against actual bank senders
4. **Harden transfer intelligence** — Improve CC payment matching and statement-total reconciliation
5. **Create the initial clean commit history** — The working tree is still pre-history and should be committed intentionally

### Medium-term
6. **Gmail OAuth setup** — Google Cloud Console, OAuth consent screen, restricted scope verification
7. **OCR fallback** — Selective low-signal page OCR is implemented; remaining work is model benchmarking on weak public-sector scans
8. **User correction learning** — When user edits merchant/category, auto-apply to future matches
9. **Multi-user auth** — Proper registration flow, password reset, email verification
10. **Family mode** — Merge spouse/family cards into shared dashboard

### Long-term
11. **Account Aggregator integration** — India's AA ecosystem (Sahamati) for direct bank data
12. **Rewards tracking** — Credit card reward points from statements
13. **Encryption at rest** — AES-256 for stored PDFs, encrypted DB columns for sensitive data
14. **Zero-retention mode** — Delete PDFs after parsing, keep only structured data
15. **iOS support** — Expo build for iOS (no SMS, but all other features)
16. **Play Store distribution** — Apply for SMS permission exception or use SMS Retriever API
17. **Automated backups** — PostgreSQL pg_dump on schedule
18. **Notification system** — Bill due date reminders, unusual spending alerts
19. **PWA** — Offline-capable web app with service worker
20. **Import from other apps** — CSV import from Walnut, Axio, Money Manager
21. **API rate limiting** — Production hardening
22. **Audit logging** — Track all data access for compliance

### Product Direction
- **Statement-first, not SMS-first** — Statements are the source of truth
- **Self-hosted, not cloud** — User owns all data
- **India-specific** — Don't try to be generic, go deep on Indian banks
- **Deterministic core** — LLM is always a fallback, never the primary logic
- **Privacy by design** — OTPs never transmitted, PII sanitized before LLM, zero-retention option

---

## 2026-03-25 Documentation Refresh
- Added root README for repository onboarding and quick-start clarity.
- Knowledge file retained as full source-of-truth transfer document.
- Next major focus remains statement ingestion robustness + reconciliation + mobile polish.

## 2026-03-25 Knowledge Transfer Compliance
- This file is the canonical transfer document for architecture, implemented scope, missing features, and future plans.
- Memory sync source: `<workspace-root>/personal-helper/memory/`.
- Shared local LLM model location and runtime assumptions must be updated here on every change.
