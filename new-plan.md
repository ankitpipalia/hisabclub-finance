# HisabClub: Phase 2 Implementation Plan

**Date**: 2026-04-06
**Scope**: 6 new features + UI/UX overhaul + extraction pipeline hardening

## Implementation Status Update

This file is still the Phase 2 source-of-truth plan, but the following blocks are now implemented in repo and live runtime:

- Implemented:
  - backend schema foundation:
    - `backend/app/models/institution.py`
    - `backend/app/models/account.py`
    - `backend/app/models/transaction_annotation.py`
    - `backend/app/models/conversation.py`
    - `backend/app/models/tax_portal_data.py`
    - `backend/app/models/balance_snapshot.py`
    - migration `backend/alembic/versions/a4b5c6d7e8f9_add_phase2_foundation_models.py`
    - migration `backend/alembic/versions/b2c3d4e5f6a7_add_balance_snapshots_and_product_views.py`
  - account linking service:
    - `backend/app/engines/account/service.py`
    - parser integration in `backend/app/engines/parser/base.py`
  - auth/onboarding/register APIs:
    - `backend/app/api/v1/auth.py`
  - account hierarchy APIs:
    - `backend/app/api/v1/accounts.py`
  - persistent assistant APIs:
    - `backend/app/api/v1/conversations.py`
  - tax portal APIs:
    - `backend/app/api/v1/tax.py`
  - net worth APIs:
    - `backend/app/api/v1/net_worth.py`
    - `backend/app/engines/insights/net_worth.py`
  - subscriptions API:
    - `backend/app/api/v1/subscriptions.py`
    - `backend/app/engines/insights/subscriptions.py`
  - statement review APIs:
    - `backend/app/api/v1/statements.py`
  - transaction workflow APIs:
    - `backend/app/api/v1/transactions.py`
    - `backend/app/models/transaction_split.py`
    - migration `backend/alembic/versions/c4d5e6f7a8b9_add_transaction_split_lineage.py`
    - transaction detail/audit payload via `GET /api/v1/transactions/{txn_id}/detail`
  - web routes/pages:
    - `frontend/src/pages/OnboardingPage.tsx`
    - `frontend/src/pages/AccountsPage.tsx`
    - `frontend/src/pages/AssistantPage.tsx`
    - `frontend/src/pages/StatementReviewPage.tsx`
    - `frontend/src/pages/TransactionsPage.tsx`
    - `frontend/src/pages/TransactionDetailPage.tsx`
    - `frontend/src/pages/TaxPage.tsx`
    - `frontend/src/pages/NetWorthPage.tsx`
    - `frontend/src/pages/SubscriptionsPage.tsx`
    - `frontend/src/pages/LoginPage.tsx`
    - `frontend/src/components/Layout.tsx`
- Verified on running backend:
  - `/api/v1/accounts/tree` returns `200` after UUID serialization fix
  - `/api/v1/conversations/{thread_id}/resolve` returns `200` after explicit refresh fix
  - disposable-user smoke test covered:
    - register/login
    - onboarding profile/banks/complete
    - accounts/accounts-tree/account-statements
    - statement review + annotate + verify + bulk-verify
    - conversations create/messages/resolve
    - tax portal-data/discrepancies
    - net-worth manual snapshot create + overview read
    - subscriptions overview read
    - transactions bulk-update and split
- Verified in local build/typecheck:
  - web transaction detail route and dashboard deep-links
  - mobile transaction bulk-update selection mode
  - mobile transaction detail edit/split/history flow
- Regression tests added:
  - `backend/tests/test_api/test_phase2_routes.py`
  - `backend/tests/test_api/test_net_worth_routes.py`
  - `backend/tests/test_insights/test_net_worth.py`
  - `backend/tests/test_insights/test_subscriptions.py`
  - `backend/tests/test_api/test_transaction_workflows.py`

Still partial relative to the full plan:
- mobile parity foundation is now implemented for onboarding/accounts/assistant/tax/review/net-worth/subscriptions, but still lacks richer document/PDF UX and advanced flows
- statement review PDF UX is now upgraded on web with `react-pdf`; mobile supports authenticated PDF handoff to native open/share but still does not embed inline PDF rendering
- broader Feature 5 UI additions such as dashboard refinement are not fully implemented
- transaction bulk edit/split is now implemented on web and backend
- transaction detail/audit is now implemented on web and mobile
- net-worth and subscriptions exist in repo, but they are not the current delivery priority

---

## 1. Current State Summary

### What's Implemented
- **Backend**: FastAPI + PostgreSQL, 27 ORM models, queue-based extraction (ExtractionJob), 6 template parsers, LLM fallback (iterative chunk + tier-2 table mapping), vision-first extraction (Qwen3-VL-8B), selective OCR, 3-tier transaction pipeline (raw → parsed → canonical), 4-tier dedup, merchant normalization (48 merchants, 90 patterns), 73 seeded categories, balance-walk validation, CC integrity gates, review tasks, correction chat, tax compliance, Gmail sync, SMS sync, folder import, RLS tenant isolation
- **Web**: React 19 + Vite + Tailwind, 18 pages (Dashboard, Upload, Transactions, Statements, Insights, Budgets, Bills, Tax, Assistant, Account, Accounts, Onboarding, Net Worth, Subscriptions, Gmail, Imports, Login, ResetPassword)
- **Mobile**: React Native + Expo SDK 55 + Paper MD3, 11 screens (Login, Dashboard, Transactions, TransactionDetail, Insights, Settings, Upload, Statements, Budgets, Bills, SMSSync)
- **LLM**: Qwen3-VL-8B-Instruct on :8096 (primary), GLM-4.1v-9b-thinking on :8095 (OCR), routed via factory.py

### What's Missing (This Plan Addresses)
- No PDF viewer in UI — users can't visually verify extracted transactions against source
- No account/institution hierarchy — statements are flat, ungrouped
- No persistent LLM conversation — assistant is stateless, single-shot
- No onboarding wizard — setup is a basic email+password form
- Limited UI information density across pages
- No tax document parsing or cross-verification with IT portal data

---

## 2. Core Extraction Pipeline — Current Logic Deep Dive

```
Upload (PDF/XLSX/CSV)
  → SHA-256 file hash dedup
  → Non-PDF → DocumentArtifact (classify, store, NO extraction yet)
  → PDF → RawPdf + ExtractionJob (queued)

Worker claims ExtractionJob (fair per-user scheduling):
  → Load RawPdf, resolve storage path + password
  → decrypt_pdf(pikepdf) → extract_text(pdfplumber)
  → assess_text_quality() → OCR fallback for empty/low-signal pages (GLM-4.1v via PyMuPDF render)
  → infer_bank_hint + infer_account_type_hint
  → score_statement_difficulty() → route model tier

  → IF vision_primary enabled:
      → llm_parse_statement_from_page_images(Qwen3-VL-8B)
        → render pages as PNG → send each to /v1/chat/completions with image
        → extract metadata + transactions per page → merge with dedup
  → ELSE: detect_parser() → template parse (HDFC/Axis/SBI CC+Savings)
      → IF 0 transactions: vision extraction → text LLM fallback

  → LLM fallback chain:
      Tier 2: extract_stitched_table_rows → LLM column mapping → deterministic row mapping
      Tier 1: chunk text (5200 chars, 6-line overlap) → LLM JSON extraction per chunk → merge

  → validate_extracted_statement():
      - drop: empty description, amount ≤ 0, invalid direction
      - drop: dates outside period (−120 to +31 days)
      - drop: exact internal duplicates
      - balance walk: opening + credits − debits ≈ closing (savings/current)
  
  → build_statement_semantic_fingerprint() → duplicate check
  → ATOMIC block:
      → create Statement record
      → for each ExtractedTransaction:
          → create ParsedTransaction (quarantine if confidence < 0.75)
          → if not quarantined: promote_to_canonical()
              → DedupEngine.find_duplicate() (4-tier: fingerprint/ref/amount+date+desc/amount+date)
              → if match: merge_source() (link parsed → existing canonical)
              → if new: normalize_merchant() → infer_category() → infer_nature() → create CanonicalTransaction
      → create ReviewTask if quarantined rows exist
      → create Bill if credit card

  Post-parse:
  → reclassify_transfer_payments (3-pass: deterministic + pairing + LLM)
  → reconcile_upi_failures (match debit ↔ credit reversals)
  → build_integrity_gates (CC: deterministic + LLM review)
  → apply_post_parse_gates (quarantine_clear, yield_rate_ok, cc_integrity_ok, balance_walk_ok)
  → upsert StatementPeriodCoverage
  → record parser support observation
  → move PDF to cold storage
```

### Key Data Flow
```
RawPdf → Statement → ParsedTransaction → TransactionSource → CanonicalTransaction
                                              ↑ dedup match
PDF page → [OCR if needed] → text → [template|LLM|vision] → ExtractedTransaction
                                                                  → validate
                                                                  → ParsedTransaction
```

### Validation Gates (Trust Model)
No LLM output directly becomes canonical. Every path goes through:
1. Pydantic schema validation (type/format)
2. Statement-level validation (dates, amounts, balance walk)
3. Confidence scoring (template=1.0, vision=0.84-0.92, LLM=0.5-0.9)
4. Quarantine gate (confidence < 0.75 → human review required)
5. Yield rate gate (extracted/expected < 0.55 → warning)
6. Integrity gate (CC: debits−credits vs total_due)
7. Dedup engine (4-tier prevents duplicate canonical records)

---

## 3. Feature 1: PDF Side-by-Side Viewer + Transaction Review

### Goal
User opens a statement, sees the original PDF on the left and extracted digital transactions on the right. Can visually verify each transaction, add comments, request LLM corrections per-transaction.

### Database Changes

**New model: `TransactionAnnotation`**
```python
# backend/app/models/transaction_annotation.py
class TransactionAnnotation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_annotations"
    
    user_id: UUID FK → users.id
    parsed_transaction_id: UUID FK → parsed_transactions.id (nullable)
    canonical_transaction_id: UUID FK → canonical_transactions.id (nullable)
    statement_id: UUID FK → statements.id
    annotation_type: String(30)  # "comment" | "correction_request" | "verification" | "flag"
    content: Text  # user's comment or correction request
    llm_response: Text | None  # LLM's response to correction
    status: String(20)  # "pending" | "applied" | "rejected" | "acknowledged"
    actions_json: JSONB | None  # structured actions taken (same format as correction_chat)
    page_number: Integer | None  # PDF page for linking
    created_at, updated_at
```

### Backend Endpoints

**File**: `backend/app/api/v1/statements.py` (extend)

```
GET /statements/{id}/review
  → Returns: statement metadata + parsed_transactions (with canonical linkage) + annotations
  → Each parsed_txn includes: line_number, page_number (inferred from line), confidence,
    is_quarantined, linked canonical_transaction (if promoted), existing annotations

POST /statements/{id}/transactions/{txn_id}/annotate
  → Body: { annotation_type, content, page_number? }
  → Creates TransactionAnnotation
  → If annotation_type == "correction_request": sends to LLM for processing
    → LLM response stored in annotation, actions proposed
    → If apply_changes=true in subsequent call, applies and records UserOverride

POST /statements/{id}/transactions/{txn_id}/verify
  → Marks transaction as user-verified (sets reviewed_at, reviewer_user_id on ParsedTransaction)

POST /statements/{id}/bulk-verify
  → Marks all transactions in statement as verified
```

### Web UI

**New page**: `frontend/src/pages/StatementReviewPage.tsx`

Route: `/statements/{id}/review`

Layout:
```
┌─────────────────────────────────────────────────────┐
│ Statement: HDFC CC · Mar 2026 · 66 transactions     │
│ [Back] [Bulk Verify] [Export]                        │
├──────────────────────┬──────────────────────────────┤
│                      │ Transaction List              │
│   PDF Viewer         │ ┌──────────────────────────┐ │
│   (react-pdf)        │ │ 05/03 SWIGGY   ₹450  DR │←│── click highlights in PDF
│                      │ │ ☑ verified  💬 1 comment │ │
│   Page 1 of 5        │ ├──────────────────────────┤ │
│                      │ │ 06/03 AMAZON  ₹2,500 DR  │ │
│   [zoom] [fit]       │ │ ⚠ quarantined (0.62)     │ │
│                      │ │ [Promote] [Ignore]        │ │
│                      │ ├──────────────────────────┤ │
│                      │ │ Comment input...    [Send]│ │
│                      │ │ [Ask LLM to fix]          │ │
│                      │ └──────────────────────────┘ │
└──────────────────────┴──────────────────────────────┘
```

Components:
- `PdfViewer` — wraps `react-pdf` (npm: `react-pdf`). Renders pages, supports zoom/fit-width, page navigation. Uses `GET /statements/{id}/pdf` for blob.
- `TransactionReviewList` — scrollable list of ParsedTransactions. Each row shows: date, description, amount, direction, confidence badge, quarantine status, verification checkbox, annotation count.
- `TransactionReviewCard` — expanded view when clicked. Shows canonical fields (if promoted), allows inline comment, correction request. Highlights corresponding region in PDF viewer via page_number.
- `AnnotationThread` — displays existing annotations + LLM responses per transaction.

**Dependency**: `npm install react-pdf` in `frontend/`

### Mobile UI

**New screen**: `mobile/src/screens/StatementReviewScreen.tsx`

Sequential layout (not split-pane):
1. Statement header with key metrics
2. Transaction list with swipe actions (verify, flag, comment)
3. Tap transaction → expanded detail with annotation input
4. "View PDF" button opens system PDF viewer via `expo-sharing` or inline `WebView`

---

## 4. Feature 2: Account & Statement Hierarchy Map

### Goal
Visual tree showing: Institution → Accounts → Statements → Transaction summaries. Users see all their financial accounts in one place.

### Database Changes

**New model: `Institution`**
```python
# backend/app/models/institution.py
class Institution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institutions"
    
    name: String(100) unique  # "HDFC Bank", "Axis Bank", "SBI"
    short_name: String(20)  # "HDFC", "AXIS", "SBI"
    logo_key: String(50) | None  # for frontend icon mapping
    institution_type: String(30)  # "bank" | "nbfc" | "broker"
    supported_formats: JSONB  # {"pdf": true, "csv": false, "xlsx": false}
    is_system: Boolean default True
```

**New model: `Account`**
```python
# backend/app/models/account.py
class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    
    user_id: UUID FK → users.id
    institution_id: UUID FK → institutions.id (nullable, for user-custom banks)
    institution_name: String(100)  # denormalized for display
    account_type: String(50)  # "savings" | "current" | "credit_card" | "fd" | "demat"
    account_number_masked: String(50) | None
    nickname: String(100) | None  # user-given name: "My Salary Account"
    status: String(20) default "active"  # "active" | "closed"
    metadata_json: JSONB | None  # bank-specific: credit limit, branch, IFSC
    last_statement_date: Date | None
    opening_date: Date | None
    
    UniqueConstraint(user_id, institution_name, account_type, account_number_masked)
```

**Modify: `Statement`** — add `account_id: UUID FK → accounts.id (nullable)` for linking.

**Seed data**: 16 Institution records for supported Indian banks (HDFC, ICICI, SBI, Axis, Kotak, BOB, PNB, Canara, Union, IndusInd, YES, Federal, IDBI, IOB, BOI, Indian Bank)

### Backend Endpoints

**File**: `backend/app/api/v1/accounts.py` (NEW)

```
GET /accounts/tree
  → Returns hierarchical data:
    [{ institution: "HDFC Bank", accounts: [
        { id, type: "savings", masked: "XX1234", nickname, 
          statement_count: 5, last_statement: "2026-03-15",
          total_transactions: 342, latest_balance: 45000.00,
          period_coverage: [{start, end}] },
        { id, type: "credit_card", masked: "XX5678", ... }
    ]}]

GET /accounts
  → Flat list of all user accounts

POST /accounts
  → Create account manually: { institution_name, account_type, account_number_masked?, nickname? }

PATCH /accounts/{id}
  → Update nickname, status, metadata

DELETE /accounts/{id}
  → Soft-delete (set status=closed), don't delete linked data

GET /accounts/{id}/statements
  → List statements for this account with summary metrics

GET /institutions
  → List available institutions (system + user-created)
```

**Auto-populate migration**: Run once to create Account records from existing Statement data:
```sql
INSERT INTO accounts (user_id, institution_name, account_type, account_number_masked)
SELECT DISTINCT user_id, bank_name, account_type, account_number_masked
FROM statements WHERE is_active = true
ON CONFLICT DO NOTHING;
```
Then backfill `statements.account_id` by matching.

**Auto-link on parse**: In `base.py`, after creating Statement, find or create matching Account and set `statement.account_id`.

### Web UI

**New page**: `frontend/src/pages/AccountsPage.tsx`

Route: `/accounts` (add to sidebar under "Primary nav")

Layout:
```
┌─────────────────────────────────────────────────┐
│ MY ACCOUNTS                            [+ Add]  │
├─────────────────────────────────────────────────┤
│ ┌─ HDFC BANK ─────────────────────────────────┐ │
│ │  🏦 Savings XX1234 "Salary Account"         │ │
│ │     5 statements · Last: Mar 2026           │ │
│ │     342 txns · Balance: ₹45,000             │ │
│ │     Coverage: ████████░░ Apr24–Mar26        │ │
│ │  💳 Credit Card XX5678                      │ │
│ │     3 statements · Last: Mar 2026           │ │
│ │     198 txns · Limit: ₹2,00,000            │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─ ICICI BANK ────────────────────────────────┐ │
│ │  🏦 Savings XX9012                          │ │
│ │     1 statement · Last: Feb 2026            │ │
│ │     186 txns · Balance: ₹1,23,456           │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

Click an account → drill-down to statement list → click statement → review page (Feature 1).

Coverage bar shows which months have statements (from StatementPeriodCoverage).

### Mobile UI

**New screen**: `mobile/src/screens/AccountsScreen.tsx`

Add as 5th bottom tab or accessible from Settings. Collapsible institution sections with account cards.

---

## 5. Feature 3: LLM Conversational Q&A

### Goal
After parsing, the LLM reviews ambiguous transactions and generates questions. Users answer in a chat interface. Conversation persists across sessions.

### Database Changes

**New model: `ConversationThread`**
```python
# backend/app/models/conversation.py
class ConversationThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_threads"
    
    user_id: UUID FK → users.id
    context_type: String(30)  # "statement_review" | "general" | "tax_review" | "onboarding"
    context_id: UUID | None  # statement_id, etc.
    title: String(200)
    status: String(20) default "active"  # "active" | "resolved" | "archived"
    pending_question_count: Integer default 0
    metadata_json: JSONB | None

class ConversationMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "conversation_messages"
    
    thread_id: UUID FK → conversation_threads.id
    role: String(20)  # "assistant" | "user" | "system"
    content: Text
    actions_json: JSONB | None  # structured actions proposed/taken
    transaction_ids: ARRAY(UUID) | None  # linked transactions for context
    created_at: DateTime(timezone=True)
```

### Backend

**Post-parse question generation**: In `runner.py`, after parse completes, if any transactions have low confidence (0.5-0.75) or ambiguous nature, trigger:

```python
# backend/app/engines/llm/question_generator.py (NEW)
async def generate_post_parse_questions(
    db, user_id, statement_id, parsed_transactions
) -> list[str]:
    """LLM reviews ambiguous transactions and generates user questions."""
```

Question types:
- Nature ambiguity: "₹5,000 on 15/03 'UPI/TRANSFER' — is this a personal transfer or a payment?"
- Category ambiguity: "3 transactions to 'AMAZON' totaling ₹8,500 — all personal, or any business?"
- Missing info: "CARD PAYMENT for ₹2,500 on 06/03 — what was this purchase for?"
- Duplicate concern: "Two ₹1,200 charges to 'SWIGGY' on the same day — are both valid?"

**Endpoints**: `backend/app/api/v1/conversations.py` (NEW)

```
GET /conversations
  → List threads with unread counts, filter by context_type/status

GET /conversations/{id}/messages
  → Paginated message history

POST /conversations/{id}/reply
  → Body: { message: string, apply_changes?: boolean }
  → Sends user reply + conversation history to LLM
  → LLM processes, may propose actions (category change, nature fix, etc.)
  → Returns LLM response + proposed/applied actions

GET /conversations/pending-count
  → Returns count of threads with unanswered questions (for notification badges)

POST /conversations/{id}/resolve
  → Mark thread as resolved
```

### Web UI

**Enhance**: `frontend/src/pages/AssistantPage.tsx` → refactor into threaded conversation UI

```
┌─────────────────────────────────────────────────┐
│ AI ASSISTANT                    🔴 3 pending    │
├──────────────┬──────────────────────────────────┤
│ THREADS      │  HDFC CC Mar 2026 Review         │
│              │                                    │
│ ● HDFC CC    │  🤖 I noticed 3 ambiguous txns:  │
│   Mar 2026   │     1. "UPI/412345" ₹5,000 DR    │
│   3 pending  │        → Transfer or payment?     │
│              │     2. "CARD PMT 67890" ₹2,500    │
│ ○ General    │        → What was this for?       │
│   corrections│                                    │
│              │  You: The UPI was rent payment     │
│ ○ ICICI Feb  │        to my landlord             │
│   resolved   │                                    │
│              │  🤖 Got it. I'll categorize as:   │
│              │     "Rent" under Housing.          │
│              │     [Apply] [Edit] [Skip]          │
│              │                                    │
│              │  [Type your message...]    [Send]  │
└──────────────┴──────────────────────────────────┘
```

### Mobile UI

**Enhance**: Add `ConversationsScreen.tsx` accessible from Dashboard. Show notification badge on bottom tab when pending questions exist.

---

## 6. Feature 4: Onboarding Wizard

### Goal
Multi-step wizard during first-time setup that collects personal info, bank accounts, and credit cards.

### Database Changes

**Modify: `User` model**
```python
# Add to user.py:
last_name: String(100) | None
pan_number_encrypted: Text | None  # AES-256 encrypted
onboarding_completed: Boolean default False
onboarding_step: String(30) | None  # track progress for resume
```

PAN validation: regex `^[A-Z]{5}\d{4}[A-Z]$`
PAN encryption: use existing `security/crypto.py` (same as Gmail token encryption)

**Account model** (from Feature 2): created during onboarding Step 3.

### Backend

**File**: `backend/app/api/v1/auth.py` (extend)

```
POST /auth/setup  → extend to accept: first_name, last_name, date_of_birth, pan_number
  → Creates User + encrypts PAN
  → Sets onboarding_completed=false

POST /auth/onboarding/profile
  → Update profile fields post-setup (if skipped during setup)

POST /auth/onboarding/banks
  → Body: { banks: [{ institution_name, accounts: [{ account_type, account_number_masked?, nickname? }] }] }
  → Creates Institution refs + Account records
  → Sets onboarding_step = "banks_complete"

POST /auth/onboarding/complete
  → Sets onboarding_completed = true

GET /auth/onboarding/status
  → Returns { completed, current_step, profile_complete, accounts_count }
```

### Web UI

**New component**: `frontend/src/pages/OnboardingPage.tsx`

Route: `/onboarding` — redirected to after first login if `onboarding_completed=false`

Steps:
```
Step 1: PERSONAL INFO
  ┌──────────────────────────────────┐
  │ First Name: [Ankit          ]    │
  │ Last Name:  [Pipalia        ]    │
  │ DOB:        [06/04/1995     ]    │
  │ PAN:        [ABCDE1234F     ]    │
  │ (PAN is encrypted, never shared) │
  │                         [Next →] │
  └──────────────────────────────────┘

Step 2: SELECT YOUR BANKS
  ┌──────────────────────────────────┐
  │ Which banks do you use?          │
  │                                  │
  │ [✓] HDFC Bank                    │
  │ [✓] ICICI Bank                   │
  │ [ ] SBI                          │
  │ [ ] Axis Bank                    │
  │ [✓] Kotak Mahindra              │
  │ ... (16 options)                 │
  │ [+ Add custom bank]             │
  │                    [← Back] [→]  │
  └──────────────────────────────────┘

Step 3: CONFIGURE ACCOUNTS (per selected bank)
  ┌──────────────────────────────────┐
  │ HDFC BANK                        │
  │                                  │
  │ Savings Accounts: [1 ▾]          │
  │   Account 1: XX____1234 (opt)    │
  │   Nickname: [Salary Account]     │
  │                                  │
  │ Credit Cards: [2 ▾]              │
  │   Card 1: XXXX____5678 (opt)     │
  │   Nickname: [Personal CC]        │
  │   Card 2: XXXX____9012 (opt)     │
  │   Nickname: [Business CC]        │
  │                                  │
  │ Current Accounts: [0 ▾]          │
  │                    [← Back] [→]  │
  └──────────────────────────────────┘
  (Repeat for each selected bank)

Step 4: CONFIRMATION
  ┌──────────────────────────────────┐
  │ You're all set!                  │
  │                                  │
  │ Profile: Ankit Pipalia           │
  │ Banks: HDFC, ICICI, Kotak       │
  │ Accounts: 3 savings, 2 CC       │
  │                                  │
  │ Next: Upload your first          │
  │ bank statement →                 │
  │                                  │
  │              [Go to Dashboard]   │
  └──────────────────────────────────┘
```

### Mobile UI

**Enhance**: `mobile/src/screens/LoginScreen.tsx` → after successful setup, navigate to `OnboardingScreen.tsx` (NEW). Same 4-step wizard adapted for mobile with swipeable steps.

---

## 7. Feature 5: Enhanced UI/UX + New Features

### Per-Page Enhancements

#### Dashboard (`DashboardPage.tsx`)
**Current**: Summary stats, pie/bar charts, upcoming bills, recent 5 transactions
**Add**:
- **Financial Health Score**: 0-100 score computed from: savings rate, bill payment timeliness, spending consistency, emergency fund coverage. Display as a large gauge/ring chart.
- **Net Worth Card**: Sum of latest balances across all accounts (from Account model). Show month-over-month change.
- **Cash Flow Forecast**: Simple 3-month projection based on recurring income/expense patterns. Line chart.
- **Quick Stats Row**: Total accounts, total statements processed, data coverage (months), last sync time.
- **Spending Alerts**: Banner for anomalous spending (> 2x average in a category).

#### Transactions (`TransactionsPage.tsx`)
**Current**: Paginated table with search, direction filter, timeline presets
**Add**:
- **Category filter dropdown**: Filter by specific category
- **Bank/account filter**: Filter by institution + account
- **Nature filter**: expense/income/transfer/refund/investment
- **Amount range filter**: Min/max sliders
- **Bulk actions**: Select multiple → bulk categorize, bulk tag, bulk exclude
- **Inline edit**: Click amount/category/nature to edit inline (currently read-only table)
- **Split transaction**: Split one transaction into multiple categories (e.g., grocery bill with household + food items)
- **Transaction grouping**: Group by date / merchant / category toggle

#### Statements (`StatementsPage.tsx`)
**Current**: Basic list with integrity checks, re-review, delete
**Add**:
- **Statement timeline**: Visual timeline showing all statements with gaps highlighted
- **Coverage gaps alert**: "You're missing HDFC CC statements for Jan 2026, Feb 2026"
- **Statement comparison**: Compare two statements side-by-side (useful for re-reviews)
- **Quick metrics**: Per-statement: extracted/promoted/quarantined counts, yield rate, extraction method used
- **Link to review page**: [Review] button → Feature 1 PDF viewer

#### Insights (`InsightsPage.tsx`)
**Current**: Monthly summary, category pie, 6-month trend bar, recurring
**Add**:
- **Merchant spending analysis**: Top 10 merchants by spend, frequency, average transaction size
- **Day-of-week/time-of-month patterns**: When do you spend most? Heatmap visualization.
- **Category trend sparklines**: Mini line charts per category showing 6-month trends
- **Savings rate tracker**: Income vs expenses ratio over time
- **YoY comparison**: This month vs same month last year
- **Subscription detector**: Enhanced recurring view with total monthly subscription cost, next payment dates

#### Budgets (`BudgetsPage.tsx`)
**Current**: Basic CRUD with progress bars
**Add**:
- **Budget vs actual chart**: Bar chart comparing budget to actual per category
- **Projected overspend alert**: "At current rate, you'll exceed Food budget by ₹2,000"
- **Historical budget adherence**: How often you stayed within budget (last 6 months)
- **Suggested budgets**: Based on historical spending patterns (LLM-assisted)

#### Bills (`BillsPage.tsx`)
**Current**: Upcoming/paid/all tabs, mark-as-paid
**Add**:
- **Payment calendar**: Monthly calendar view showing bill due dates
- **Auto-detect from transactions**: When a CC payment matches a bill's due amount, auto-mark as paid
- **Reminder settings**: Days-before-due notification preference
- **Total monthly obligations**: Sum of all upcoming bills

#### Tax (`TaxPage.tsx`)
**Current**: FY selector, new-regime calculation, document coverage, transfer reconciliation
**Add**:
- **Old regime comparison**: Show tax under both old and new regime, recommend better option
- **TDS tracker**: Track TDS deducted (from salary, interest, etc.) vs tax liability
- **Advance tax schedule**: Show due dates (Jun 15, Sep 15, Dec 15, Mar 15) with amounts
- **Section-wise deduction input**: 80C, 80D, 80G, HRA (for old regime comparison)
- **Tax portal verification section**: Feature 6 (below)

#### Upload (`UploadPage.tsx`)
**Current**: Drag-drop with bank/doctype/password config
**Add**:
- **Upload history with filters**: Search/filter by bank, status, date
- **Bulk re-process**: Re-process all failed uploads
- **Password memory**: Remember password patterns per bank (already has backend support via InstitutionPasswordPattern)
- **Upload progress**: Real-time extraction status with SSE or polling (queued → extracting → validating → done)
- **Drag-drop organization**: Auto-detect bank from filename patterns

#### Account (`AccountPage.tsx`)
**Current**: Profile display, change password, clear data
**Add**:
- **Edit profile**: First name, last name, DOB, PAN (from onboarding)
- **Connected accounts list**: Show Gmail connections, SMS sync status
- **Data statistics**: Total statements, transactions, storage used
- **Export options**: Full data export (JSON), GDPR-style data download
- **Session management**: Active sessions, logout all devices

### New Pages

#### Net Worth (`frontend/src/pages/NetWorthPage.tsx`)
Route: `/net-worth`
- Track balances across all accounts over time
- Line chart showing net worth progression
- Asset breakdown: savings accounts, FDs, investments
- Liability breakdown: CC outstanding, loans
- Manual entry for assets not tracked by statements (property, gold, etc.)

**Backend**: New model `BalanceSnapshot` (user_id, account_id, balance, as_of_date, source). Auto-populate from statement closing_balance. Endpoint: `GET /net-worth/history`, `POST /net-worth/manual-entry`

#### Subscriptions (`frontend/src/pages/SubscriptionsPage.tsx`)
Route: `/subscriptions`
- Detected recurring payments with logos/names
- Monthly/annual cost totals
- "Cancel risk" flag for unused subscriptions (no activity besides charge)
- Calendar view of next charge dates
- Track price changes over time

**Backend**: Extend `RecurringPattern` with: is_subscription flag, service_category, last_charge_date, price_change_history. Endpoint: `GET /subscriptions`

### Mobile-Only Enhancements

- **Tax screen**: Port TaxPage to mobile (currently missing)
- **Assistant/Chat screen**: Port conversation UI to mobile
- **Accounts screen**: Port account hierarchy view
- **Widgets**: Android home screen widget showing monthly spend, upcoming bills
- **Biometric auth**: Fingerprint/face unlock via `expo-local-authentication`
- **Push notifications**: For new LLM questions, bill reminders, anomaly alerts

---

## 8. Feature 6: Tax Portal Integration

### Goal
Parse Form 26AS, AIS, TIS, Form 16 documents to extract structured tax data, then cross-verify against app-calculated values.

### Tax Document Parsers

**File**: `backend/app/engines/tax/` (NEW directory)

#### Form 26AS Parser (`form_26as_parser.py`)
Extracts:
- Part A: TDS by employer/deductors (TAN, amount, tax deducted, deposited)
- Part A1: TDS on income other than salary
- Part A2: TDS on sale of property
- Part B: Tax collected at source
- Part C: Tax paid (advance tax, self-assessment)
- Part D: Paid refunds
- Part F: SFT (high-value transactions)

Input: PDF (downloaded from TRACES portal) or CSV
Output: `Form26ASData` Pydantic model with structured entries

#### AIS Parser (`ais_parser.py`)
Extracts:
- TDS/TCS information
- SFT (Specified Financial Transactions): savings interest, FD interest, mutual fund purchases/redemptions, share transactions, property, high-value purchases
- Other information: foreign remittances, cash deposits/withdrawals

Input: PDF or CSV (both formats available from portal)
Output: `AISData` Pydantic model

#### Form 16 Parser (`form16_parser.py`)
Extracts:
- Part A: Employer TDS certificate (employer details, TAN, tax deducted quarterly)
- Part B: Detailed salary breakup, deductions claimed, tax computation

Input: PDF
Output: `Form16Data` Pydantic model

### Cross-Verification Engine

**File**: `backend/app/engines/tax/verification.py` (NEW)

```python
async def cross_verify_tax(
    db, user_id, financial_year
) -> TaxVerificationReport:
    """Compare app-calculated tax data with IT portal documents."""
```

Comparisons:
| Check | App Source | Portal Source | Tolerance |
|-------|-----------|---------------|-----------|
| Total income | CanonicalTransaction (nature=income) | AIS TDS entries + Form 16 Part B | ₹1,000 |
| Salary income | Transactions matching salary keywords | Form 16 Part B gross salary | ₹500 |
| Interest income | Savings interest (from statements) | AIS SFT interest entries | ₹100 |
| TDS deducted | Computed from known TDS rules | Form 26AS Part A total | ₹100 |
| Advance tax paid | Manual entries or bank debits | Form 26AS Part C | ₹0 (exact) |
| High-value txns | Transactions > ₹10L | AIS SFT entries | Flag for review |

Output: `TaxVerificationReport` with per-check status (match/mismatch/unverified), discrepancy amounts, and action items.

### Backend Endpoints

**File**: `backend/app/api/v1/tax.py` (NEW router)

```
POST /tax/upload-portal-document
  → Upload Form 26AS/AIS/TIS/Form 16
  → Parse and store structured data in DocumentArtifact + new TaxPortalData model

GET /tax/verification/{fy}
  → Run cross-verification, return report

GET /tax/portal-data/{fy}
  → Return parsed portal data for display

GET /tax/discrepancies/{fy}
  → Return only mismatched items with suggested actions
```

**New model: `TaxPortalData`**
```python
class TaxPortalData(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tax_portal_data"
    
    user_id: UUID FK → users.id
    financial_year: String(10)  # "2025-26"
    document_type: String(30)  # "form_26as" | "ais" | "tis" | "form_16"
    artifact_id: UUID FK → document_artifacts.id
    parsed_data: JSONB  # structured extraction result
    verification_status: String(20) default "pending"  # "pending" | "verified" | "discrepancies_found"
```

### Web UI Enhancement

**Extend**: `frontend/src/pages/TaxPage.tsx`

Add new sections:
```
┌─────────────────────────────────────────────────┐
│ TAX & AUDIT · FY 2025-26                        │
├─────────────────────────────────────────────────┤
│ TAX COMPUTATION                                  │
│  Total Income: ₹12,50,000                        │
│  New Regime Tax: ₹97,500                         │
│  Old Regime Tax: ₹1,15,000 (with deductions)    │
│  → New Regime saves ₹17,500                      │
├─────────────────────────────────────────────────┤
│ PORTAL VERIFICATION                    [Upload]  │
│  ┌──────────────────────┬──────────┬──────────┐ │
│  │ Check                │ App Data │ Portal   │ │
│  ├──────────────────────┼──────────┼──────────┤ │
│  │ Total Income         │ ₹12.5L  │ ₹12.48L  │ │
│  │ Salary               │ ₹10.0L  │ ₹10.0L ✓│ │
│  │ Interest Income      │ ₹45,000 │ ₹47,200 ⚠│ │
│  │ TDS Deducted         │ ₹1.2L   │ ₹1.18L ⚠│ │
│  │ Advance Tax          │  —      │ ₹0      ✓│ │
│  └──────────────────────┴──────────┴──────────┘ │
│  ⚠ 2 discrepancies found. Missing: BOB FD       │
│    interest ₹2,200 not in app data.              │
├─────────────────────────────────────────────────┤
│ DOCUMENT COVERAGE                                │
│  Form 16:    ✓ Uploaded   26AS: ✓ Uploaded      │
│  AIS:        ✓ Uploaded   TIS:  ✗ Missing       │
└─────────────────────────────────────────────────┘
```

---

## 9. Consolidated Database Schema Changes

### New Models (6)

| Model | Table | Purpose |
|-------|-------|---------|
| `Institution` | `institutions` | Bank/NBFC registry with metadata |
| `Account` | `accounts` | User-linked financial accounts |
| `TransactionAnnotation` | `transaction_annotations` | Comments/corrections on transactions |
| `ConversationThread` | `conversation_threads` | Persistent chat threads with LLM |
| `ConversationMessage` | `conversation_messages` | Individual messages in threads |
| `TaxPortalData` | `tax_portal_data` | Parsed IT portal documents |

### Modified Models (2)

| Model | Changes |
|-------|---------|
| `User` | +last_name, +pan_number_encrypted, +onboarding_completed, +onboarding_step |
| `Statement` | +account_id FK → accounts |

### Alembic Migration

Single migration file covering all changes. Order:
1. Create `institutions` table + seed 16 banks
2. Create `accounts` table
3. Alter `users` (add columns)
4. Alter `statements` (add account_id)
5. Create `transaction_annotations`
6. Create `conversation_threads` + `conversation_messages`
7. Create `tax_portal_data`
8. Data migration: auto-populate accounts from existing statements, backfill statement.account_id

---

## 10. New Files Summary

### Backend
| Path | Purpose |
|------|---------|
| `backend/app/models/institution.py` | Institution model |
| `backend/app/models/account.py` | Account model |
| `backend/app/models/transaction_annotation.py` | Annotation model |
| `backend/app/models/conversation.py` | Thread + Message models |
| `backend/app/models/tax_portal_data.py` | Tax portal data model |
| `backend/app/api/v1/accounts.py` | Account CRUD + tree endpoint |
| `backend/app/api/v1/conversations.py` | Chat thread endpoints |
| `backend/app/api/v1/tax.py` | Tax verification endpoints |
| `backend/app/engines/llm/question_generator.py` | Post-parse LLM question generation |
| `backend/app/engines/tax/form_26as_parser.py` | Form 26AS parser |
| `backend/app/engines/tax/ais_parser.py` | AIS/TIS parser |
| `backend/app/engines/tax/form16_parser.py` | Form 16 parser |
| `backend/app/engines/tax/verification.py` | Cross-verification engine |
| `backend/app/schemas/accounts.py` | Account request/response schemas |
| `backend/app/schemas/conversations.py` | Conversation schemas |
| `backend/app/schemas/tax.py` | Tax verification schemas |
| `backend/alembic/versions/xxxx_phase2_features.py` | Migration |

### Frontend (Web)
| Path | Purpose |
|------|---------|
| `frontend/src/pages/StatementReviewPage.tsx` | PDF viewer + transaction review |
| `frontend/src/pages/AccountsPage.tsx` | Account hierarchy map |
| `frontend/src/pages/OnboardingPage.tsx` | Multi-step onboarding wizard |
| `frontend/src/pages/NetWorthPage.tsx` | Net worth tracking |
| `frontend/src/pages/SubscriptionsPage.tsx` | Subscription management |
| `frontend/src/components/PdfViewer.tsx` | react-pdf wrapper component |
| `frontend/src/components/TransactionReviewCard.tsx` | Per-transaction review card |
| `frontend/src/components/AnnotationThread.tsx` | Annotation display |
| `frontend/src/components/OnboardingWizard.tsx` | Step wizard component |
| `frontend/src/components/FinancialHealthScore.tsx` | Health score gauge |
| `frontend/src/components/CoverageBar.tsx` | Statement coverage visualization |

### Mobile
| Path | Purpose |
|------|---------|
| `mobile/src/screens/StatementReviewScreen.tsx` | Statement review (sequential layout) |
| `mobile/src/screens/AccountsScreen.tsx` | Account hierarchy |
| `mobile/src/screens/OnboardingScreen.tsx` | Onboarding wizard |
| `mobile/src/screens/ConversationsScreen.tsx` | LLM chat threads |
| `mobile/src/screens/TaxScreen.tsx` | Tax compliance + verification |

---

## 11. Implementation Priority

### Phase A — Foundation (do first, enables everything else)
1. Database migration (all new models + alterations)
2. Account/Institution models + auto-populate from existing data
3. Onboarding wizard (web + mobile)
4. Account tree endpoint + AccountsPage

### Phase B — Core Features
5. PDF side-by-side viewer (web) — `react-pdf` integration + review endpoints
6. TransactionAnnotation model + annotation endpoints
7. Statement review page with PDF ↔ transaction linking
8. Conversation model + threaded chat endpoints
9. Post-parse LLM question generation
10. Enhanced AssistantPage with threads

### Phase C — Tax & Verification
11. Tax document parsers (Form 26AS, AIS, Form 16)
12. Cross-verification engine
13. Tax page enhancements (old/new regime, portal verification)
14. TaxPortalData model + upload endpoints

### Phase D — UI/UX Polish
15. Dashboard enhancements (health score, net worth card, cash flow)
16. Transaction page enhancements (filters, bulk actions, inline edit)
17. Insights enhancements (merchant analysis, patterns)
18. Budget/Bills enhancements
19. Net Worth page
20. Subscriptions page
21. Mobile parity (Tax, Assistant, Accounts screens)

---

## 12. Verification Plan

### Per-feature testing:
- **Accounts**: Create via onboarding → verify tree endpoint → verify statement linkage → verify coverage bar
- **PDF viewer**: Upload PDF → open review → verify PDF renders → verify transaction list matches → add annotation → verify LLM processes correction
- **Conversations**: Parse statement → verify LLM generates questions → answer in chat → verify changes applied
- **Onboarding**: Fresh setup → complete wizard → verify User fields saved → verify Accounts created → verify redirect to dashboard
- **Tax verification**: Upload Form 26AS → verify parsing → run cross-verification → verify discrepancy detection
- **Enhanced UI**: Visual check each page → verify new components render → verify data accuracy

### Automated tests:
```bash
cd backend && python -m pytest tests/ -v
```

New test files needed:
- `tests/test_models/test_account.py`
- `tests/test_api/test_accounts.py`
- `tests/test_api/test_conversations.py`
- `tests/test_api/test_tax.py`
- `tests/test_tax/test_form_26as_parser.py`
- `tests/test_tax/test_ais_parser.py`
- `tests/test_tax/test_verification.py`
- `tests/test_llm/test_question_generator.py`

---

## 13. What This Does NOT Change

- llama.cpp runtime, TurboQuant, model quantization, model files
- Existing 6 template parsers (HDFC/Axis/SBI CC+Savings)
- Core extraction pipeline logic (parse_statement orchestrator)
- Dedup engine, fingerprinting, merchant normalization
- Gmail sync, SMS sync pipelines
- RLS policies, security model
- Existing API contracts (all changes are additive)
