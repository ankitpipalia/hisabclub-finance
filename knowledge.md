# HisabClub — Complete Project Knowledge Transfer

## What is HisabClub?

A **privacy-first, self-hosted Indian personal finance ledger**. Users upload credit card and bank statement PDFs (password-protected), optionally sync Android SMS transaction alerts, and the app merges all sources into a unified ledger with automatic categorization, spending insights, bill tracking, and budget management.

**Core differentiators:**
- Indian bank statement expertise (HDFC, Axis, SBI parsers)
- Password-protected PDF handling (pikepdf decryption)
- Cross-source reconciliation (statement + SMS dedup)
- Self-hosted (all data stays on your server)
- Deterministic core logic, LLM only as feature-flagged fallback
- Privacy-first: OTPs and personal messages never leave the device

**Production URL:** `https://hisabclub-dev-api.ankit-tech.store` (Cloudflare Zero Trust tunnel → `192.168.1.69:8000`)

**User credentials:** `desibabubro@gmail.com` / `Ankit@2002`

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
│   Web Frontend  │───▶│   FastAPI Backend    │◀───│  LLM (QwQ-32B)  │
│   React + Vite  │    │   Python 3.10       │    │  llama.cpp      │
│   Port 5173 dev │    │   Port 8000         │    │  Port 8080      │
│   Served from   │    │   Serves API + SPA  │    └─────────────────┘
│   backend /     │    └──────────┬──────────┘
└─────────────────┘               │
                        ┌─────────┴─────────┐
                        │                   │
                   ┌────▼────┐        ┌────▼────┐
                   │ Postgres│        │  Redis  │
                   │ Port 5433│        │Port 6380│
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
| **LLM** | llama.cpp server + QwQ-32B (Q4_K_M) | - |
| **Containers** | Docker Compose | - |

---

## Directory Structure

```
/home/ankit/Documents/personal-finance-app/
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
│   │   ├── models/                    # SQLAlchemy ORM (18 tables)
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
│   │   │   ├── insights.py           # MonthlySummary + RecurringPattern
│   │   │   └── __init__.py           # Exports ALL models (MUST be updated when adding models)
│   │   │
│   │   ├── schemas/                   # Pydantic request/response
│   │   │   ├── auth.py, statement.py, transaction.py, upload.py
│   │   │   ├── sms.py, budget.py, bill.py, insights.py
│   │   │
│   │   ├── api/v1/                    # FastAPI routers (27 endpoints)
│   │   │   ├── router.py             # Aggregates ALL routers (MUST update when adding)
│   │   │   ├── auth.py               # POST /setup, /login, GET /me
│   │   │   ├── upload.py             # POST /pdf (with debug text saving)
│   │   │   ├── statements.py         # GET list + detail
│   │   │   ├── transactions.py       # GET list + detail, PATCH update, GET sources
│   │   │   ├── categories.py         # GET list
│   │   │   ├── merchants.py          # GET list with search
│   │   │   ├── sms.py                # POST /batch (bulk SMS import)
│   │   │   ├── insights.py           # GET monthly-summary, trends, recurring
│   │   │   ├── budgets.py            # CRUD budgets with spent calculation
│   │   │   ├── bills.py              # CRUD bills (status: upcoming/unpaid/paid/all)
│   │   │   ├── export.py             # GET /csv (StreamingResponse)
│   │   │   └── gmail.py              # OAuth connect, callback, sync, allowlist
│   │   │
│   │   ├── engines/                   # Core business logic
│   │   │   ├── parser/               # Statement parsing engine
│   │   │   │   ├── base.py           # StatementParser ABC, registry, parse_statement() orchestrator
│   │   │   │   │                     # Includes LLM fallback when template returns 0 txns
│   │   │   │   ├── pdf_utils.py      # pikepdf decrypt + pdfplumber text extraction
│   │   │   │   ├── amount_utils.py   # parse_indian_amount() handles C prefix, Rs., INR, ₹
│   │   │   │   │                     # parse_indian_date() handles DD/MM/YYYY, DD-MMM-YYYY etc.
│   │   │   │   ├── ocr.py            # Tesseract fallback (stub)
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
│   │   │   │   ├── sanitizer.py       # Strip PII before LLM (cards, names, PAN, Aadhaar)
│   │   │   │   ├── parse_fallback.py  # LLM parses unknown PDF layouts → ExtractedStatement
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
│   │   └── tasks/                     # Background tasks (stubs for ARQ worker)
│   │
│   └── tests/                         # Test structure (stubs)
│       ├── conftest.py
│       ├── fixtures/
│       ├── test_parser/, test_ledger/, test_api/
│
├── frontend/                          # React + Vite + TailwindCSS web app
│   ├── package.json
│   ├── vite.config.ts                 # Proxy /api → :8000, allowedHosts for tunnel
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.tsx                   # Entry point
│   │   ├── index.css                  # Tailwind import
│   │   ├── App.tsx                    # Routes: /, /upload, /transactions, /statements,
│   │   │                              #   /insights, /budgets, /bills, /gmail
│   │   ├── api/
│   │   │   └── client.ts             # ApiClient class + all type interfaces
│   │   │                              # getBills/getBudgets unwrap {items} from response
│   │   ├── components/
│   │   │   └── Layout.tsx            # Sidebar nav + main content + Export CSV button
│   │   └── pages/
│   │       ├── LoginPage.tsx
│   │       ├── DashboardPage.tsx      # Summary cards + PieChart + BarChart + bills + recent txns
│   │       ├── UploadPage.tsx         # Drag-drop PDF + password + bank hint
│   │       ├── TransactionsPage.tsx   # Filterable paginated table
│   │       ├── StatementsPage.tsx     # Statement cards
│   │       ├── InsightsPage.tsx       # Full analytics: PieChart, BarChart, recurring, top merchants
│   │       ├── BudgetsPage.tsx        # Budget progress bars + create/delete
│   │       ├── BillsPage.tsx          # Upcoming/Paid tabs + mark paid + due badges
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
│   │   │   ├── LoginScreen.tsx        # Server URL + email/password + autofill-friendly
│   │   │   ├── DashboardScreen.tsx    # Summary + bills + categories + quick actions + recent txns
│   │   │   ├── TransactionsScreen.tsx # Infinite scroll + search + filter
│   │   │   ├── TransactionDetailScreen.tsx # View + edit category/notes
│   │   │   ├── UploadScreen.tsx       # Document picker + CC/Bank type + password hint
│   │   │   ├── StatementsScreen.tsx
│   │   │   ├── InsightsScreen.tsx     # Category bars + recurring + top merchants
│   │   │   ├── BudgetsScreen.tsx      # Progress bars + FAB create dialog
│   │   │   ├── BillsScreen.tsx        # Segmented filter + due badges + mark paid
│   │   │   ├── SettingsScreen.tsx     # Server URL, quick access, SMS sync link, logout
│   │   │   └── SmsSyncScreen.tsx      # Permission request, Sync Now, Preview, history
│   │   ├── sms/                       # On-device SMS processing (privacy-first)
│   │   │   ├── bankPatterns.ts        # 30+ sender IDs, regex patterns, amount/date extraction
│   │   │   ├── SmsFilterer.ts         # Classification + spam scoring (requires account reference)
│   │   │   ├── SmsParser.ts           # Extract amount, direction, account, UPI ref
│   │   │   ├── SmsSyncService.ts      # Orchestrator: read → filter → parse → POST /sms/batch
│   │   │   ├── SmsBridge.ts           # Platform gate (PermissionsAndroid for popup)
│   │   │   └── types.ts
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
├── models/                            # LLM model files
│   └── qwq-32b-q4_k_m.gguf          # 19.8GB, Qwen QWQ 32B Q4_K_M quantization
│
├── uploads/                           # User-uploaded PDFs (gitignored)
│
├── infra/docker/                      # Infrastructure templates (stubs)
│
├── docker-compose.yml                 # PostgreSQL 16 (:5433) + Redis 7 (:6380)
├── docker-compose.llm.yml            # Optional: llama.cpp server (image: ghcr.io/ggml-org/llama.cpp:server)
├── start-llm.sh                      # Script to start LLM via Docker (GPU issues — use native instead)
├── Makefile                           # Dev commands (uses backend/.venv/bin)
├── .env                               # Active config (LLM_ENABLED=true, ports 5433/6380)
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

## API Endpoints (27 routes)

### Auth (`/api/v1/auth`)
| Method | Path | Description |
|---|---|---|
| POST | `/setup` | First-time user creation (blocks if user exists) |
| POST | `/login` | Returns JWT access + refresh tokens |
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

### Transactions (`/api/v1/transactions`)
| Method | Path | Description |
|---|---|---|
| GET | `/` | List (filters: from, to, bank, direction, category_id, min/max_amount, search, page, per_page) |
| GET | `/{id}` | Detail with category name |
| PATCH | `/{id}` | Update (category_id, merchant_id, notes, tags, is_excluded) — creates override audit |
| GET | `/{id}/sources` | Source lineage (which statement/SMS contributed) |

### Categories (`/api/v1/categories`) — GET list
### Merchants (`/api/v1/merchants`) — GET list with search

### SMS (`/api/v1/sms`)
| POST | `/batch` | Bulk import parsed SMS ({device_id, items[]}) with sms_hash dedup |

### Insights (`/api/v1/insights`)
| GET | `/monthly-summary?month=` | Income/expense/net + category breakdown + top merchants + vs_last_month |
| GET | `/trends?months=6` | Multi-month trend data for charts |
| GET | `/recurring` | Detected recurring transactions |
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

### Running Natively (NOT Docker — GPU passthrough issues)
```bash
llama-server \
  --model /home/ankit/Documents/personal-finance-app/models/qwq-32b-q4_k_m.gguf \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 4096 --n-gpu-layers 99
```

### Model Details
- **File**: `/home/ankit/Documents/personal-finance-app/models/qwq-32b-q4_k_m.gguf` (19.8 GB)
- **Model**: Qwen QWQ-32B, Q4_K_M quantization
- **GPU**: NVIDIA RTX A5000 (24GB VRAM) — all 65 layers offloaded
- **Performance**: ~27 tokens/sec
- **API**: OpenAI-compatible at `http://localhost:8080/v1`

### Docker Alternative (if GPU passthrough works)
```bash
docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d llm
```
Image: `ghcr.io/ggml-org/llama.cpp:server`
Note: NVIDIA Container Toolkit is installed but `--gpus all` had CDI issues.

### LLM Usage in App
- **Feature-flagged**: `LLM_ENABLED=true` in `.env`
- **Fallback for 0-transaction parsing**: When template parser returns 0 transactions
- **Merchant normalization**: Clean up messy raw merchant descriptions
- **Category suggestion**: Pick best category from list
- **PII sanitized** before any LLM call (cards, names, PAN, Aadhaar, OTPs stripped)
- **QwQ is a reasoning model**: Needs higher max_tokens (500+) for chain-of-thought

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

### Backend
```bash
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info   # Start
.venv/bin/alembic upgrade head                                                  # Apply migrations
.venv/bin/alembic revision --autogenerate -m "description"                     # New migration
.venv/bin/python -m app.seed.run                                               # Seed categories + merchants
```

### Web Frontend
```bash
cd frontend
npm run dev           # Dev server on :5173 (NOT for production via tunnel)
npx vite build        # Build to dist/ (served by backend at /)
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

### Docker Services
```bash
docker compose up -d                 # Start PostgreSQL + Redis
docker compose down                  # Stop
docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d llm  # LLM (if GPU works)
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

## Known Issues & Not Working

### Critical
1. **HDFC CC parser total_due/min_due/credit_limit not parsing** — The Swiggy HDFC card puts these in a non-standard table layout where fields like `TOTAL AMOUNT DUE`, `MINIMUM DUE`, `CREDIT LIMIT` are on a header row and values are on the next row with `C` prefix. The regex looks for them on the same line. Transactions (15) parse correctly though.

2. **`expo prebuild` wipes native customizations** — Every time `npx expo prebuild --platform android --clean` runs, the Kotlin SMS reader files and MainApplication.kt changes are lost. Must re-copy and re-edit manually.

3. **ADB streamed install intermittently fails** — Use `adb push + pm install` workaround instead of `adb install`.

### SMS
4. **SMS native module untested on device** — The Kotlin ContentResolver code was written but the actual SMS reading hasn't been verified on a physical device with real bank SMS. The PermissionsAndroid dialog works.

5. **SMS sync doesn't run in background yet** — The `expo-task-manager` + `expo-background-fetch` setup is coded but hasn't been tested. Manual "Sync Now" works.

### Backend
6. **Gmail OAuth not configured** — `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` are empty. Need Google Cloud Console setup with OAuth consent screen.

7. **No tests written** — Test structure exists but no actual test files.

8. **Redis not used** — Redis is running but no caching or task queue is implemented. ARQ worker is stub only.

9. **No multi-user support in practice** — Auth works but features like shared household dashboards aren't built.

10. **Docker GPU passthrough broken** — NVIDIA Container Toolkit installed but `--gpus all` gives CDI error. LLM runs natively as workaround.

### Frontend
11. **InsightsPage/BudgetsPage/BillsPage may have edge cases** — Built by agents, not thoroughly manually tested.

12. **No PWA support** — Web app doesn't work offline.

13. **Git repo has 0 commits** — All code is untracked.

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
1. **Fix HDFC metadata extraction** — Parse total_due, min_due, credit_limit from the table format
2. **Write tests** — Parser unit tests with sample PDF text, API integration tests
3. **Initial git commit** — Commit all code, set up .gitignore properly
4. **Test SMS on real device** — Verify native module reads actual bank SMS
5. **Background SMS sync** — Test and enable expo-task-manager periodic sync

### Medium-term
6. **More bank parsers** — ICICI CC, Kotak CC, Yes Bank, IndusInd, AMEX India
7. **Gmail OAuth setup** — Google Cloud Console, OAuth consent screen, restricted scope verification
8. **OCR fallback** — Tesseract for scanned/image-based PDFs
9. **Settlement matching** — Match CC bill payment (bank debit) to CC statement total
10. **User correction learning** — When user edits merchant/category, auto-apply to future matches
11. **Multi-user auth** — Proper registration flow, password reset, email verification
12. **Family mode** — Merge spouse/family cards into shared dashboard

### Long-term
13. **Account Aggregator integration** — India's AA ecosystem (Sahamati) for direct bank data
14. **Rewards tracking** — Credit card reward points from statements
15. **Encryption at rest** — AES-256 for stored PDFs, encrypted DB columns for sensitive data
16. **Zero-retention mode** — Delete PDFs after parsing, keep only structured data
17. **iOS support** — Expo build for iOS (no SMS, but all other features)
18. **Play Store distribution** — Apply for SMS permission exception or use SMS Retriever API
19. **Automated backups** — PostgreSQL pg_dump on schedule
20. **Notification system** — Bill due date reminders, unusual spending alerts
21. **PWA** — Offline-capable web app with service worker
22. **Import from other apps** — CSV import from Walnut, Axio, Money Manager
23. **API rate limiting** — Production hardening
24. **Audit logging** — Track all data access for compliance

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
- Memory sync source: `/home/ankit/Documents/personal-helper/memory/`.
- Llama/QwQ model location and runtime assumptions must be updated here on every change.
