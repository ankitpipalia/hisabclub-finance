# HisabClub Phase 3 — Refactor: Correctness, UI/UX, and Test Harness

## Context

Phase 2 (now in repo) delivered the feature surface: accounts/onboarding, persistent conversations, statement review, net worth, subscriptions, tax verification, transaction split/audit, BOB savings deterministic parser. The Phase 2 plan is preserved at `/home/ankit/Documents/personal-finance-app/new-plan.md` and is the source-of-truth feature catalog.

Phase 3 hardens the foundation across three pillars:

1. **Correctness & validation** — the new `app/extraction/` module is authoritative for the statement parse path, but secondary write paths (SMS import, review-resolve, manual approve/correct) bypass its typed validation and silently overwrite `validation_status` on `CanonicalTransaction`. Plus 8 other concrete bugs surfaced by the audit (float SQL comparison in dedup tiers 2/3, fragile balance-walk index coupling, LLM chunk failures silently dropped, dual validation pipelines with divergent semantics, sanitizer over-masks bare UPI refs, `is_credit=None` dropped instead of routed-to-review, missing chunk-failure metadata, "CARD PAYMENT" still nature-misclassified in some cases).

2. **UI/UX** — there is **no animation library installed** on either platform. Web has CSS keyframes only (`hc-fade-up`, `.hc-stagger` capped at 7 children) and uses `window.confirm()` for destructive actions. Mobile uses the legacy RN `Animated` API (no Reanimated, no Moti, no haptics, no gestures). iOS support exists in `app.json` but lacks icon/splash/infoPlist config and pod-install discipline. No skeleton states, no toasts, no modals on either platform.

3. **Testing** — backend has 182 tests but **no E2E harness against real data**, **no frontend tests**, **no mobile tests**. The SMS and review-resolve audit gaps are regression-untested. Real test data exists at `/home/ankit/Documents/FY24-25-Ankit-details/` (41 files / 9.9 MB across HDFC, Kotak, ICICI, SBI, BOB, plus Form-16 + demat exports) — this is real PII, must stay local, and must be opt-in via `RUN_REAL_E2E=1`.

Outcome target: a hardened pipeline with no silent-loss paths, a polished motion-rich UI on iOS+Android+web, and a multi-tier test harness that includes real-data smoke tests gated behind an env flag.

---

# Workstream 1 — Core correctness & validation refactor

## 1.1 Findings (with file:line evidence)

### Confirmed bugs

| ID | File:Line | Issue | Severity |
|---|---|---|---|
| W1.1 | `backend/app/engines/ledger/merger.py:116-117` | `promote_to_canonical()` hardcodes `validation_status="valid", validation_errors=None`, erasing audit when SMS/review-resolve flow through it | HIGH |
| W1.2 | `backend/app/api/v1/sms.py:30-122` | SMS path creates `RawSms` + `ParsedTransaction` and calls `promote_to_canonical()` — dedup IS invoked but the new `app/extraction/validator.py` is **not**; no review tasks generated for SMS-quality issues | MEDIUM |
| W1.3 | `backend/app/api/v1/reviews.py:128-171` | `resolve` action with `promote` — dedup IS invoked but typed validation is bypassed; `approve`/`correct` actions force `validation_status="valid"` overwriting prior audit | MEDIUM |
| W1.4 | `backend/app/engines/ledger/dedup.py:149, 198` | Tiers 2/3 use `CanonicalTransaction.amount == float(parsed_txn.amount)` — float SQL comparison is unsafe at boundary cases; should use `Decimal` quantized to 2 dp | MEDIUM |
| W1.5 | `backend/app/extraction/validator.py:146-176` + `backend/app/extraction/promoter.py:135-162` | `BalanceWalkResult.problematic_txns` returns indices that today happen to align with the `new_txns` insertion order — fragile by coincidence; if a future caller reorders, drift is silent | MEDIUM |
| W1.6 | `backend/app/extraction/promoter.py:74-81` | `if txn.is_credit is None: continue` — drops the transaction even when validation_status is `NEEDS_REVIEW`; should route to review with assumed direction + flag | MEDIUM |
| W1.7 | `backend/app/engines/llm/parse_fallback.py:143-157` | LLM chunk-level failures (`payload is None` or schema-invalid) silently `continue`; no metadata about which chunks failed surfaced to caller or `Statement.parse_errors` | MEDIUM |
| W1.8 | `backend/app/engines/llm/sanitizer.py:70-90` | Reference-context regex requires nearby keywords (`UPI`/`UTR`/etc) within ~18 chars; standalone 12-digit RRNs/UTRs and isolated UPI refs are masked | LOW-MED |
| W1.9 | `backend/app/engines/parser/validation.py` (legacy) + `backend/app/extraction/validator.py` (new) | Both run sequentially in `parse_statement` (base.py:717 then promoter); legacy is permissive, new is strict; divergence allowed for silent drops | MEDIUM |

### Already-fixed (verified during audit, no action needed)
- C2 (account isolation in dedup tiers) — **fixed** at `dedup.py:124-127, 155-158, 204-207`
- C8 (Tier 1 ref match honors direction) — **fixed** at `dedup.py:118-122` (the older audit was wrong)
- C4 (balance walk for bank accounts) — **fixed** by `extraction/validator.py:146-176` + `extraction/promoter.py:116-126` (legacy merger path still skips, but only secondary writers use it)

### Reuse — existing utilities to lean on
- `app/extraction/validator.py:dedup_key()` — SHA256 of normalized fields (paise + description prefix + direction + account)
- `app/extraction/validator.py:parse_decimal_amount()` — Indian format Decimal parsing
- `app/extraction/validator.py:resolve_credit_flag()` — DR/CR disambiguation
- `app/extraction/validator.py:validate_transaction()` — typed validation
- `app/engines/ledger/fingerprint.py:build_transaction_dedupe_fingerprint()` — paise-based fingerprint
- `app/engines/ledger/dedup.py:DedupEngine` — already invoked from `promote_to_canonical`

## 1.2 Implementation order

### Stage A — Foundation (additive, no behavior change)

**A1. Extend `promote_to_canonical()` signature** — `backend/app/engines/ledger/merger.py:24-132`
- Add three keyword-only parameters with defaults preserving current behavior:
  - `validation_status: str = "valid"`
  - `validation_errors: list[str] | None = None`
  - `balance_walk_passed: bool | None = None`
- Replace hardcodes at lines 116-117 with parameter values; pass `balance_walk_passed` to `CanonicalTransaction` constructor (column already exists at `canonical_transaction.py:72` but isn't set today).
- Add log-line including `validation_status` for audit visibility.

**A2. Introduce shared review-task helper** — new `backend/app/engines/ledger/review_helpers.py`
- Extract review-task creation logic from `extraction/promoter.py:159-188` into `create_review_task_for_canonical(db, parsed, canonical, reasons, statement_id=None)`.
- `statement_id` kwarg is `None` for SMS/manual paths; verify `review_tasks.statement_id` is currently NOT NULL — if so, add Alembic migration `add_nullable_statement_id_to_review_tasks.py` to drop the constraint (additive, reversible).

### Stage B — Bypass-path correctness (CRITICAL)

**B1. Route SMS through typed validation** — `backend/app/api/v1/sms.py`
- Replace the inline ParsedTransaction construction (lines 70-90) with:
  1. Build `RawTransaction` via `app.extraction.adapter.dict_to_raw_transaction()` with `source=ExtractionSource.SMS` (add this enum value to `extraction/models.py`).
  2. Call `validate_transaction(raw)` from `extraction/validator.py`.
  3. If `validation_status == INVALID`: mark error, append SmsBatchItemResult error, skip.
  4. Persist `ParsedTransaction` with `is_quarantined=True` if `LOW_CONFIDENCE` or `NEEDS_REVIEW`.
  5. Call `promote_to_canonical()` with explicit `validation_status=`, `validation_errors=` from validator output.
  6. If validator flagged `NEEDS_REVIEW` or `LOW_CONFIDENCE`, call `create_review_task_for_canonical()` (statement_id=None).
- Use `parse_decimal_amount(item.amount)` instead of raw float.

**B2. Wire dedup-result + validation-status into review-resolve** — `backend/app/api/v1/reviews.py:128-171`
- Inside `if action == "promote":` branch (line 137):
  - `promote_to_canonical(...)` already invokes dedup. Surface the result: if `existing` (i.e., merged), increment a new `merged` counter; otherwise increment `promoted` as today.
  - Pass through the parsed_txn's existing validation_status (read from associated `extraction_audit` columns if available, else "valid" since user explicitly approved).
  - Add `merged_count` field to `ResolveReviewTaskResponse` schema (`backend/app/schemas/review.py`) — additive, frontend can adopt later.
- For `approve` (line 174-186) and `correct` (line 189+) actions: before overwriting `txn.validation_status="valid"`, archive prior status into `task.payload_json["prior_validation"] = {status, errors}` to preserve audit chain.

**B3. Fix Tier 2/3 float SQL comparison** — `backend/app/engines/ledger/dedup.py:146-203`
- Replace `CanonicalTransaction.amount == float(parsed_txn.amount)` with `CanonicalTransaction.amount == parsed_txn.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
- Pass `Decimal` instead of `float()` cast at line 49 (fingerprint construction) — `build_transaction_dedupe_fingerprint` already converts internally via `_to_paise(Decimal(str(amount)))`.
- Add defensive `(parsed_txn.description_raw or "").upper()` at line 167 to handle null descriptions.

### Stage C — Pipeline robustness

**C1. Stable balance-walk problem identifiers** — `backend/app/extraction/validator.py:146-176`
- Change `BalanceWalkResult.problematic_txns: list[int]` to `list[BalanceWalkProblem]` where `BalanceWalkProblem` is a dataclass with `index_in_input`, `txn_date`, `amount`, `description_prefix`. This breaks the fragile coupling to insertion order.
- Update `extraction/promoter.py:135-162` to compare via tuple identity, not list membership of integer indices.
- Update `tests/test_extraction/test_balance_walk.py:80-88` accordingly.

**C2. Allow NEEDS_REVIEW with `is_credit=None`** — `backend/app/extraction/promoter.py:74-81`
- Split the conditional: only drop on `INVALID`. For `is_credit is None` AND not INVALID:
  - Set `txn.validation_status = NEEDS_REVIEW`
  - Append `"cr_dr_resolved"` to `validation_errors`
  - Heuristic-default `is_credit = False` (debit) so promotion can proceed
  - This guarantees `_review_reasons` (lines 396-413) fires the `needs_review` reason and a ReviewTask is created
- Document the heuristic in code comment: "ambiguous direction defaults to debit; user resolves via review/correct flow"

**C3. LLM chunk failure metadata** — `backend/app/engines/llm/parse_fallback.py:143-157`
- Track `failed_empty_chunks: list[int]` and `failed_schema_chunks: list[int]` during the loop.
- Append a structured warning to `ExtractedStatement.warnings`: `f"LLM extraction partial: {len(failed)}/{len(chunks)} chunks failed (indices: {failed})"`.
- Return these via a new field on the function result; persist into `Statement.parse_errors["llm_chunks"] = {total, failed_empty, failed_schema}` in `parse_statement` orchestrator (`base.py` around line 778-790).

**C4. Sanitizer — preserve UPI-shaped refs** — `backend/app/engines/llm/sanitizer.py:70-90`
- Inside `_mask_sensitive_numeric_id`: precheck for known reference shapes BEFORE applying the generic masker:
  - 12 digits, first digit != 0, not all-same, not sequential ramp → preserve (UPI RRN/UTR shape)
  - 16 digits ONLY masked if surrounding ±40 chars contain explicit `card`/`account`/`ending`/`a/c` context; otherwise preserve (UPI batch IDs are also 16 digits)
- Widen context window from ±18 to ±40 chars.

**C5. Collapse legacy validation pipeline** — `backend/app/engines/parser/validation.py` + `backend/app/engines/parser/base.py:717`
- Move statement-period balance-walk preview into new `app/extraction/balance_preview.py:summarize(opening, closing, raw_txns)` returning the same dict shape today's `validate_extracted_statement` writes to `parse_errors["validation"]["balance_walk"]` (preserves frontend/insights readers).
- Keep `validate_extracted_statement` as a thin shim that ONLY drops obviously-broken rows (date None, amount ≤ 0, direction not in {debit,credit}, empty description) — same drops the typed pipeline would do.
- Cut over via feature flag `extraction_unified_validation_enabled: bool = False` in `app/config.py`. When False: today's behavior. When True: shim only.
- Audit upstream readers BEFORE flipping flag: `app/engines/insights/statement_integrity.py`, `app/api/v1/statements.py`, frontend statement-detail rendering.

### Stage D — Feature flags & rollback

Add to `app/config.py`:
- `sms_typed_validation_enabled: bool = False` (gates B1)
- `extraction_unified_validation_enabled: bool = False` (gates C5)
- `extraction_review_keeps_ambiguous_direction: bool = False` (gates C2)
- `sanitizer_preserve_short_refs: bool = False` (gates C4)

Each flag defaults to current behavior. Cut over per environment after one release of soak time. Remove flags after second release.

## 1.3 Tests added per fix

| Fix | New / extended test |
|---|---|
| A1 | `tests/test_ledger/test_merger_validation_status.py` — assert defaults preserve "valid", explicit args propagate to row |
| B1 | `tests/test_api/test_sms_typed_validation.py` — POST same SMS twice asserts duplicate; SMS amount=0 asserts INVALID and no canonical; SMS confidence=0.4 asserts review_task created |
| B2 | extend `tests/test_api/test_phase2_routes.py` — quarantined txn whose amount/date/account already exists as canonical: resolve→promote returns `merged_count > 0` |
| B3 | extend `tests/test_extraction/test_dedup.py` — Decimal precision boundary (`0.1 + 0.2`), high-decimal-place edge cases |
| C1 | extend `tests/test_extraction/test_balance_walk.py` — pass txns in non-monotonic date order, assert `BalanceWalkProblem` identifies stable rows |
| C2 | extend `tests/test_extraction/test_promoter.py` — txn with ambiguous direction asserts `direction="debit"`, NEEDS_REVIEW status, ReviewTask with `cr_dr_resolved` reason |
| C3 | extend `tests/test_llm/test_parse_fallback.py` — mock LLM returns None for chunk 1 of 3, assert `ExtractedStatement.warnings` mentions chunk 1 |
| C4 | extend `tests/test_llm/test_sanitizer_refs.py` — standalone 12-digit ref preserved, 16-digit card with distant context still masked |
| C5 | new `tests/test_extraction/test_legacy_shim.py` — moves cases from `test_statement_validation.py` and `test_ocr_validation.py`; pipeline regression test |

---

# Workstream 2 — UI/UX overhaul (web + mobile)

## 2.1 Library installs

### Web (`frontend/package.json`)
- `motion` (~12.x) — successor to framer-motion, lighter (~32KB), `motion.div`, `AnimatePresence`, `useReducedMotion`
- `@radix-ui/react-dialog` (~1.1.x) — accessible modal primitive (replaces `window.confirm()`)
- `@radix-ui/react-tooltip` (~1.1.x)
- `sonner` (~1.7.x) — toast library, ~3KB
- `react-use-measure` (~2.1.x) — for animated chart resizing

### Mobile (`mobile/package.json`)
- `react-native-reanimated` (~4.1.x, Expo SDK 55-pinned) — UI-thread animations, layout animations
- `react-native-gesture-handler` (~2.30.x) — required by Reanimated for gesture-driven anims
- `moti` (~0.30.x) — declarative wrapper over Reanimated for stagger
- `expo-haptics` (~15.0.x) — iOS+Android tactile feedback
- `@gorhom/bottom-sheet` (~5.x) — bottom sheet primitive
- Defer until assets exist: `lottie-react-native`, `@shopify/react-native-skia`

## 2.2 iOS enablement (`mobile/`)

- `mobile/app.json`:
  - `expo.ios.supportsTablet: true`
  - `expo.ios.userInterfaceStyle: "automatic"`
  - `expo.ios.icon` → new `mobile/assets/ios-icon.png` (1024×1024)
  - `expo.ios.splash` block mirroring Android
  - `expo.ios.infoPlist`: `NSAppTransportSecurity` (allow http for local dev), `NSPhotoLibraryUsageDescription` (PDF picker), `NSCameraUsageDescription` (future)
- `mobile/eas.json`: add `ios` build profiles with `simulator: true` for development/preview
- Feature gate SMS-only paths: `Platform.OS === 'android'` checks in `mobile/src/sms/*` and `SmsSyncScreen.tsx` shows iOS empty-state ("Use Gmail or Upload instead")
- `mobile/index.ts`: `import 'react-native-gesture-handler';` as the FIRST import
- Create `mobile/babel.config.js` with `plugins: ['react-native-reanimated/plugin']` as the LAST plugin (Expo default `babel-preset-expo` first)
- Run `cd mobile/ios && pod install` after native deps; document in `mobile/README.md`

## 2.3 Web component primitives (under `frontend/src/components/ui/`)

| File | Purpose |
|---|---|
| `MotionConfig.tsx` | App-root wrapper; sets default ease/duration; plumbs `useReducedMotion` |
| `PageTransition.tsx` | Route-level fade+slide via `AnimatePresence mode="wait"` |
| `StaggerContainer.tsx` | Replaces capped `.hc-stagger`; unlimited children via motion variants |
| `AnimatedListItem.tsx` | Per-row enter/exit, supports stagger via index×40ms |
| `Skeleton.tsx`, `SkeletonPanel.tsx`, `TableSkeleton.tsx` | Shimmer loaders matching `.hc-panel` and `.hc-table` |
| `Toast.tsx` + `toast.ts` | Sonner Toaster + thin success/error/info wrappers |
| `Modal.tsx`, `ConfirmDialog.tsx` | Radix Dialog + motion overlay; replaces `window.confirm()` |
| `Tooltip.tsx` | Radix Tooltip + scale-fade |
| `MotionButton.tsx` | `whileTap`/`whileHover`; reuses `.hc-btn` classes |
| `Spinner.tsx`, `ProgressBar.tsx` | Replace `.hc-animate-spin`; smooth scaleX progress |
| `AnimatedNumber.tsx` | Tweened currency / count-up via `useMotionValue` |
| `Dropzone.tsx` | Drag-state animations for Upload page |
| `EmptyState.tsx` | Animated SVG + text fade |

## 2.4 Mobile component primitives (under `mobile/src/components/ui/`)

| File | Purpose |
|---|---|
| `MotionProvider.tsx` | Wraps app with `GestureHandlerRootView` + Reanimated defaults |
| `AnimatedCard.tsx` | Reanimated `FadeInDown` entering + scale-on-press |
| `HapticButton.tsx` | `expo-haptics` impact + scale spring on tap |
| `Skeleton.tsx`, `SkeletonRow.tsx` | Reanimated worklet shimmer |
| `ToastBanner.tsx` | Top-anchored banner with `useSyncExternalStore`-backed mini-store |
| `BottomSheet.tsx` | `@gorhom/bottom-sheet` with HC-themed handle/background |
| `AnimatedListItem.tsx` | Stagger via index×35ms, layout animations on add/remove |
| `AnimatedNumber.tsx`, `AnimatedProgress.tsx` | Shared-value tweens |
| `EmptyState.tsx` (replace existing) | Breathing SVG via `react-native-svg` + Reanimated |
| `SwipeRow.tsx` | Pan-to-reveal actions for transactions/statements |
| `PressableScale.tsx` | Generic scale-on-press without haptics |

The existing `mobile/src/components/AnimatedOrbs.tsx` and `FadeInView.tsx` keep their public API; internals rewritten to Reanimated for consistency.

## 2.5 Design token additions

### `frontend/src/index.css` — extend `:root` and dark theme:
- Duration tokens: `--hc-dur-fast: 200ms`, `--hc-dur-normal: 350ms`, `--hc-dur-slow: 600ms`
- Easing variants: `--hc-ease-emphasized`, `--hc-ease-accelerate`, `--hc-ease-decelerate`, `--hc-ease-bounce` (preserves current `--hc-ease` as alias)
- Elevation: `--hc-elev-0` through `--hc-elev-pop` (preserves zero-radius poster aesthetic)
- New keyframes: `@keyframes hc-shimmer`, `@keyframes hc-shake`, `@keyframes hc-pulse`
- Utility classes: `.hc-skeleton`, `.hc-shake`, `.hc-pulse-once`
- Preserve existing `prefers-reduced-motion` block

### `mobile/src/theme/AppThemeProvider.tsx` — extend
- Add `motion` namespace: `durations`, `easings` (Reanimated `Easing.bezier` instances), `elevation`, `shadow`, `stagger`
- Light vs dark only diverge on shadow opacity

## 2.6 Tier-1 page retrofits

### Web (Tier 1: highest visibility)

**Dashboard (`frontend/src/pages/DashboardPage.tsx`)**
- Replace plain "Loading dashboard…" with composed skeletons matching real card heights (no layout shift)
- Wrap in `<PageTransition>`; replace `.hc-stagger` with `<StaggerContainer staggerChildren={0.06}>`
- Stat-card amounts → `<AnimatedNumber>` count-up
- Recharts: `animationBegin={150}`, `animationDuration={650}`; charts in `whileInView` motion divs
- Recent transactions rows → `<AnimatedListItem index={i}>`
- "Export CSV" button → `<MotionButton>` with `<Spinner>` swap; on success `toast.success("Export ready")`
- Empty state → `<EmptyState>` with breathing SVG + "Upload your first statement" CTA

**StatementReview (`frontend/src/pages/StatementReviewPage.tsx`)**
- Split skeleton: `<TableSkeleton rows={10}>` left + PDF block skeleton right
- `<AnimatePresence mode="wait">` keyed on `selectedTxn.id` for right-pane swap
- PDF page change: `<motion.div key={pageNumber}>` 180ms fade
- Annotation submit: replace inline error/status with toasts
- Verify success: row flashes accent border 300ms (`.hc-pulse-once`)
- Annotations list → `<AnimatedListItem>` with `<AnimatePresence>` for new items

**Upload (`frontend/src/pages/UploadPage.tsx`)**
- Replace inline drop area with `<Dropzone>` primitive; drag-over: border `var(--hc-accent)`, scale 1.01, label change
- File queue → `<AnimatedListItem>` with `layout` prop for smooth reorder/removal
- Per-file `<ProgressBar>`; indeterminate during upload
- Notifications panel → `AnimatePresence` list; status transition animates left-edge accent stripe + icon flip
- On success → `toast.success(\`${fileName} parsed\`)`

**Login + Onboarding (`frontend/src/pages/LoginPage.tsx`, `OnboardingPage.tsx`)**
- Form fields stagger 50ms steps
- Mode toggle (signin/setup/forgot) → `<AnimatePresence mode="wait">` 200ms cross-fade with y:6
- Submit → `<MotionButton>` with spinner swap; on error: shake animation; on success: toast then navigate
- AppLogo: subtle breathing pulse (scale 1↔1.04, 4s ease-in-out) — Login background only
- Onboarding step transitions: direction-aware (forward x:30→0, back x:-30→0); stepper underline scaleX

### Mobile (Tier 1)

**Dashboard (`mobile/src/screens/DashboardScreen.tsx`)**
- Loading state: `<SkeletonRow count={3}/>` + 4× `<Skeleton variant="block" height={92}/>`
- Stat cards → `<AnimatedCard delay={i*60}/>`; values in `<AnimatedNumber>`
- Top-categories bar widths → Reanimated `withSpring` when summary arrives
- Recent transactions → `Animated.FlatList` with `<SwipeRow>` revealing "Mark verified" / "Open detail"
- Long-press → `expo-haptics` selection feedback
- Pull-to-refresh → custom Reanimated header with elastic + threshold haptic
- Empty state → `<EmptyState>` with animated savings-jar SVG
- Active tab icon: scale 1→1.12 spring on focus

**StatementReview (`mobile/src/screens/StatementReviewScreen.tsx`)**
- Skeleton: 8× `<SkeletonRow>`
- Selected detail: Reanimated `entering={FadeIn} exiting={FadeOut}` keyed on `selectedTxnId`
- Verify button: `<HapticButton intensity="success">`; row flashes overlay 500ms (`withSequence`)
- Bulk verify: replace `Alert.alert` with `<BottomSheet>` confirmation at 30% snap point
- Replace `Alert.alert` errors with `toast.show({type: 'error'})`

**Upload (`mobile/src/screens/UploadScreen.tsx`)**
- File picker: `<HapticButton intensity="light">`
- Selected files: `<AnimatedListItem>` with `layout`; `SlideOutRight` on remove
- Per-file `<AnimatedProgress>`; success row flashes accent
- Notifications: `<AnimatedListItem>` with `FadeInUp`; replace `Alert.alert` with `<ToastBanner>`
- Empty state: `<EmptyState>` with bouncing arrow at "Pick file"

**Login + Onboarding**
- AnimatedOrbs rewritten to Reanimated for perf; existing API preserved
- Form fields stagger via `<AnimatedListItem index>`
- Mode toggle: Moti `<MotiView from/animate/exit>` keyed on mode
- Submit: `<HapticButton>` medium intensity; success/error feedback + horizontal shake on error
- Onboarding: per-step direction-aware Reanimated transitions; active step dot scale 1↔1.4

## 2.7 Performance constraints

- Animate `transform` and `opacity` only; never `width/height/top/left` except wrapped in motion `layout` (FLIP)
- Web: `LazyMotion` with `domAnimation` features only (drops ~15KB vs `domMax`)
- Web: lists virtualized; only stagger first viewport (~12 rows); subsequent rows zero-delay
- Mobile: all anims on UI thread via Reanimated worklets; cancel animations on `useFocusEffect` blur (esp. Login orbs)
- Both: distinguish first-load (animate) vs refetch (no animate); gate on `isLoading` not `isFetching`
- Reduced motion: `MotionConfig reducedMotion="user"` on web; `AccessibilityInfo.isReduceMotionEnabled()` on mobile (read once in `MotionProvider`); primitives short-circuit
- Recharts: `isAnimationActive` true on first mount, false on subsequent updates

## 2.8 Files modified summary (Workstream 2)

| Path | Change |
|---|---|
| `frontend/package.json` | + motion, radix-dialog, radix-tooltip, sonner, react-use-measure |
| `frontend/src/App.tsx` | Wrap with `<MotionConfig>`, `<Toaster>`, `<PageTransition>` |
| `frontend/src/index.css` | Add duration/easing/elevation tokens, shimmer/shake/pulse keyframes |
| `frontend/src/components/Layout.tsx` | Adopt motion patterns for sidebar |
| `frontend/src/pages/StatementsPage.tsx:115`, `AccountPage.tsx:91` | Replace `window.confirm` with `<ConfirmDialog>` |
| ~14 frontend pages | Tier-1/2/3 retrofits per phase |
| `mobile/babel.config.js` | NEW — Reanimated plugin |
| `mobile/index.ts` | Gesture handler import (first) |
| `mobile/app.json`, `mobile/eas.json` | iOS support config |
| `mobile/package.json` | + reanimated, gesture-handler, moti, haptics, bottom-sheet |
| `mobile/src/App.tsx` | `<GestureHandlerRootView>` + `<MotionProvider>` |
| `mobile/src/theme/AppThemeProvider.tsx` | Motion tokens |
| ~11 mobile screens | Tier-1/2/3 retrofits |
| `mobile/src/components/FadeInView.tsx`, `AnimatedOrbs.tsx` | Rewrite on Reanimated; preserve API |

---

# Workstream 3 — Test harness

## 3.1 Test pyramid

### Backend (`backend/tests/`)
- **Unit (existing 182 tests, ≤ 5s total)**: keep + add bug-regression tests (see Workstream 1 §1.3)
- **Integration (Postgres-backed, ≤ 60s)** — new `tests/test_integration/`:
  - `test_sms_typed_validation.py` — duplicate detection across PDF+SMS, validation_status round-trip
  - `test_review_resolve_dedup.py` — quarantined→promote merges into existing canonical
  - `test_reimport_signature.py` — same PDF uploaded twice → second is dedup'd
  - `test_dlq_retry_flow.py` — push DLQ → retry runner → state transitions
  - `test_account_autopopulation.py` — multiple statements → Account rows materialize correctly
  - `test_conversation_e2e.py` — thread create → reply with apply_changes → resolve
- **E2E (real-data, opt-in via `RUN_REAL_E2E=1`)** — new `tests/test_e2e/`:
  - `test_real_folder_import.py` — full FY24-25 folder import; assertions on aggregates
  - `test_real_per_bank.py` — parametrized per-bank cases (HDFC, Kotak savings, Kotak CC, ICICI savings, ICICI FD, ICICI TDS, SBI savings, BOB savings, Form-16 A/B, Form-12BB, Demat Groww/Zerodha/ICICI Direct)

### Web (`frontend/`)
- **Unit (Vitest + jsdom)** — `src/api/client.test.ts`, `src/components/Layout.test.tsx`, page utility tests
- **Component (Vitest + RTL + MSW)** — sample for LoginPage, UploadPage, StatementReviewPage; expand later
- **E2E (Playwright Chromium)** — `e2e/auth.spec.ts`, `onboarding.spec.ts`, `upload.spec.ts`, `statement-review.spec.ts`, `transactions.spec.ts`, `tax.spec.ts`, `net-worth.spec.ts`

### Mobile (`mobile/`)
- **Unit (Jest + jest-expo preset)** — `src/api/client.test.ts`, `src/sms/parser.test.ts`, `src/utils/*.test.ts`, hooks/auth tests
- **Component (RTL native)** — sample for LoginScreen, UploadScreen, SmsSyncScreen
- **E2E (Maestro, NOT Detox)** — `mobile/.maestro/login.yaml`, `onboarding.yaml`, `upload.yaml`, `sms-sync.yaml`, `statement-review.yaml`. Reason: Maestro runs on Linux + Android emulator without macOS dependency; Detox iOS coverage requires macOS runner that isn't available.

## 3.2 E2E real-data harness design

Reuses `app.engines.intake.folder_importer.import_folder` (the same dependency used by `backend/scripts/import_folder_for_user.py`).

### `tests/test_e2e/conftest.py`
- `pytest_collection_modifyitems` hook: skip everything under `test_e2e/` unless `RUN_REAL_E2E=1`
- `real_data_root` (session): reads `HISABCLUB_E2E_FOLDER` env (default `/home/ankit/Documents/FY24-25-Ankit-details`); skip if missing
- `e2e_db_session` (function): opens session, applies RLS, sets `set_request_user_context` for ephemeral user
- `e2e_user` (function): creates fresh user; cascades delete on teardown
- `password_map` (session): reads `HISABCLUB_E2E_PASSWORD_MAP` JSON; never logged
- `import_real_folder` (function): wraps `import_folder()` with `parse_supported=True`, `force_reprocess=True`

### `test_real_folder_import.py`
Single async test asserting:
- `result.discovered >= 35` (tolerance for file drift)
- `result.failed == 0`
- `result.by_doc_type` contains expected categories (bank_statement, credit_card_statement, interest_certificate, form16, form12bb, tax_challan, demat_holdings, ppf_statement, fd_statement)
- `build_tax_compliance_report(FY24-25)`: `total_income > 0`, `documented_interest_income > 0`, `documented_tax_payments > 0`, `savings_account_count >= 4`
- Canonical txn count ≥ 200 (canary)

### `test_real_per_bank.py`
Parametrized cases per file; each asserts:
- `result.parsed == 1` (or `result.ingested == 1` for non-parsed types)
- Correct `by_doc_type[expected_doc_type] == 1`
- Statements: canonical txn count ≥ `min_txns`
- Snapshot compare: aggregated, non-PII shape (period, opening/closing balance, txn_count_per_month, top-5 description frequencies) saved to `tests/test_e2e/snapshots/<bank>.json` — these snapshots ARE committable since they're aggregates.
- `RUN_REAL_E2E_UPDATE=1` rewrites snapshots

## 3.3 Per-bank parametrized parser tests

New `backend/tests/test_parser/test_template_per_bank.py`:
- Parametrized over a `CASES` list of `(bank, parser, fixture_glob, snapshot_dir)` tuples
- Existing per-bank tests (`test_bob_savings_template.py`, `test_credit_card_parsers.py`) stay untouched

### Golden output JSON format
`backend/tests/test_parser/snapshots/<bank>/<fixture>.json`:
```
{
  "metadata": { bank_name, account_masked, period_start, period_end, opening_balance, closing_balance, currency },
  "transactions": [ {date_iso, description_normalized, amount, txn_type, balance_after, page_number} ],
  "validation": { is_valid, balance_walk_ok, problematic_indices }
}
```
Decimals as strings, deterministic, diffable in PRs. Helper: `tests/test_parser/_snapshot.py:assert_matches_snapshot(actual, path, update=os.getenv("UPDATE_SNAPSHOTS")=="1")`

### Synthetic fixture expansion
Extend `backend/tests/fixtures/generate_fixtures.py` with edge-case variants per bank:
- `<bank>_multimonth.pdf` — 3-month statements with carry-over balance
- `<bank>_misspelled_headers.pdf` — typo'd column headers
- `<bank>_partial_page.pdf` — last page truncated mid-row
- `<bank>_footer_noise.pdf` — repeated footer interspersed
- `<bank>_missing_balance.pdf` — rows without balance column
- `<bank>_currency_edges.pdf` — Indian grouping `1,00,000.00`, parenthesized negatives, Cr/Dr suffixes

## 3.4 Frontend Vitest + Playwright setup

### Dependencies (`frontend/package.json` devDeps)
- `vitest`, `@vitest/coverage-v8`, `@vitest/ui`
- `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`
- `jsdom`, `msw`, `@playwright/test`

### Files to create
- `frontend/vitest.config.ts` — extends Vite config, `environment: "jsdom"`, `setupFiles: ["./src/test/setup.ts"]`
- `frontend/src/test/setup.ts` — jest-dom, MSW server, jsdom polyfills, mocks `react-pdf` to `<div data-testid="pdf-stub" />`
- `frontend/src/test/msw/handlers.ts` — handlers for auth, onboarding, upload, statements, transactions, conversations
- `frontend/src/test/fixtures/*.ts` — typed mock payloads aligned with Pydantic schemas
- `frontend/playwright.config.ts` — `webServer` runs dev server, single Chromium project, `expect.toHaveScreenshot.threshold = 0.2`
- `frontend/e2e/*.spec.ts` — onboarding, upload-and-review, statement review

### Sample tests
- `src/pages/__tests__/LoginPage.test.tsx` — login flow with MSW intercepts
- `src/pages/__tests__/UploadPage.test.tsx` — file picker mock + upload polling
- `src/pages/__tests__/StatementReviewPage.test.tsx` — annotation, bulk verify, conversation reply

### npm scripts
- `test`, `test:watch`, `test:ui`, `test:coverage`, `e2e`, `e2e:ui`, `e2e:install`

### MSW vs real backend
- Vitest: MSW always
- Playwright: real backend (CI uses docker-compose)

## 3.5 Mobile Jest + Maestro setup

### Dependencies (`mobile/package.json` devDeps)
- `jest`, `jest-expo`, `@types/jest`, `@testing-library/react-native`, `@testing-library/jest-native`, `react-test-renderer`
- Maestro CLI (OS-level binary, not npm)

### Files to create
- `mobile/jest.config.js` — `preset: "jest-expo"`, transformIgnorePatterns extended for paper/expo packages
- `mobile/jest.setup.js` — mocks `expo-secure-store`, `expo-document-picker`, `expo-file-system`, `@react-native-async-storage/async-storage`, react-navigation helpers
- `mobile/src/test/utils/renderWithProviders.tsx` — wraps screen in QueryClient, NavigationContainer, PaperProvider, SafeAreaProvider
- `mobile/src/test/msw-native.ts` — MSW for native mirroring web handlers
- `mobile/.maestro/{login,onboarding,upload,sms-sync,statement-review}.yaml`
- `mobile/.maestro/README.md` — Linux Android emulator setup

### Sample tests
- `src/screens/__tests__/LoginScreen.test.tsx`, `UploadScreen.test.tsx`, `SmsSyncScreen.test.tsx`
- `src/sms/__tests__/parser.test.ts` — SMS regex/classifier with sample bank SMS strings (HDFC debit, Kotak credit, ICICI OTP, Axis CC spend)

### npm scripts
- `test`, `test:watch`, `test:coverage`, `e2e` (`maestro test .maestro`)

## 3.6 CI restructure (`.github/workflows/ci.yml`)

Replace single `backend-tests` job with:
- `backend-fast` — synthetic fixtures only, ≤90s
- `backend-integration` — Postgres testcontainer, ≤4 min
- `frontend-unit` — Vitest with coverage, ≤60s
- `frontend-e2e` — docker-compose backend + Playwright, ≤6 min
- `mobile-unit` — Jest with coverage, ≤90s
- `mobile-e2e-android` — gated on label `run-mobile-e2e` or schedule, non-blocking, ≤15 min

Markers in `pyproject.toml`:
```
markers = ["e2e: real-data tests, opt-in via RUN_REAL_E2E", "integration: DB-backed"]
```

PR runs everything except mobile-e2e-android. Main runs full set including mobile-e2e (non-blocking). Nightly cron runs visual regression. **Real-data E2E never runs in CI** — local-only via `make e2e-real`.

Backend parallelization: `pytest -n auto` via `pytest-xdist` (add as dev dep).

## 3.7 Anonymization tooling (deferred until anonymized fixtures needed)

`backend/scripts/anonymize_pdf.py` — produces committable derivatives of real PDFs preserving bank-specific quirks while replacing PII with deterministic synthetic equivalents.

Key design points:
- Per-bank profiles in `backend/scripts/anonymize_profiles/<bank>.yaml` with XY zones for PII regions
- Seeded `Faker("en_IN")` for deterministic replacement (same input → same output)
- Replaces at PDF stream level via pikepdf to preserve layout
- Validates by re-parsing anonymized output and confirming `transactions_count == original` and `closing_balance == original`
- Refuses to write if PII regex still matches in extracted text (defense in depth)
- Pre-commit hook `scripts/check_no_pii.sh` blocks PRs containing PII

Outputs (committable):
- `backend/tests/fixtures/anonymized/<bank>/<doc>.pdf` (≤3 pages each, 1–2 per profile)
- `backend/tests/test_parser/snapshots/<bank>/anon_<doc>.json` golden outputs

This is **Phase J** — last in the test harness rollout, deferred until earlier phases prove value.

---

# Implementation order (sequential phases)

The user said "start the implementation" — phases are sized for incremental landing.

| Phase | Workstream | Scope | Days |
|---|---|---|---|
| **P1** | W1 Stage A | Foundation: extend `promote_to_canonical` signature, add review-task helper, alembic migration if needed | 1 |
| **P2** | W1 Stages B+C (with feature flags off) | All correctness fixes behind flags; add bug-regression tests | 3 |
| **P3** | W3 §3.1 unit + integration | Backend integration suite, regression tests for fixed bugs | 2 |
| **P4** | W2 §2.1+§2.2 | Install motion libs (web + mobile); enable iOS; create `babel.config.js`; pod install | 1 |
| **P5** | W2 §2.3+§2.4+§2.5 | Build component primitives (web + mobile); add design tokens | 3 |
| **P6** | W2 §2.6 (Tier 1) | Retrofit Dashboard, StatementReview, Upload, Login, Onboarding (web + mobile, parallelizable) | 4 |
| **P7** | W3 §3.4 | Frontend Vitest + Playwright setup with sample tests | 2 |
| **P8** | W3 §3.5 | Mobile Jest + Maestro setup with sample tests | 2 |
| **P9** | W3 §3.2 | E2E real-data harness using `/home/ankit/Documents/FY24-25-Ankit-details` | 2 |
| **P10** | W3 §3.3 + W3 fixture expansion | Per-bank parametrized parser tests + edge-case fixtures | 2 |
| **P11** | W2 §2.6 (Tier 2) | Retrofit Transactions, Assistant, Accounts (web + mobile) | 2 |
| **P12** | W3 §3.6 | CI restructure with marker-based job split + time budgets | 1 |
| **P13** | W2 §2.6 (Tier 3) | Apply primitives to Tax, Bills, Budgets, Subscriptions, NetWorth, Insights, Gmail, Imports, Account | 3 |
| **P14** | W1 §1.2 Stage D cutover | Flip feature flags one-by-one over a release; soak; remove flags | 1 |
| **P15** (deferred) | W3 §3.7 | Anonymization tooling + committed anonymized fixtures | 3 |

Total active work: ~30 days, with P3+P4 and P5+P6 parallelizable across two engineers.

---

# Critical files to modify

### Workstream 1
- `backend/app/engines/ledger/merger.py` — A1 signature extension
- `backend/app/api/v1/sms.py` — B1 typed validation routing
- `backend/app/api/v1/reviews.py` — B2 dedup result surfacing
- `backend/app/engines/ledger/dedup.py` — B3 Decimal comparison
- `backend/app/extraction/validator.py` — C1 BalanceWalkProblem dataclass
- `backend/app/extraction/promoter.py` — C2 NEEDS_REVIEW with assumed direction
- `backend/app/engines/llm/parse_fallback.py` — C3 chunk failure metadata
- `backend/app/engines/llm/sanitizer.py` — C4 short-ref preservation
- `backend/app/engines/parser/validation.py` + `base.py:717` — C5 legacy collapse
- `backend/app/config.py` — feature flags
- New: `backend/app/engines/ledger/review_helpers.py`, `backend/app/extraction/balance_preview.py`
- Possibly: alembic migration to drop `review_tasks.statement_id` NOT NULL

### Workstream 2
- `frontend/package.json`, `frontend/src/App.tsx`, `frontend/src/index.css`, `frontend/src/components/Layout.tsx`
- New: `frontend/src/components/ui/{MotionConfig,PageTransition,StaggerContainer,AnimatedListItem,Skeleton,SkeletonPanel,TableSkeleton,Toast,toast,Modal,ConfirmDialog,Tooltip,MotionButton,Spinner,ProgressBar,AnimatedNumber,Dropzone,EmptyState}.tsx`
- 14 frontend pages (Tier 1/2/3 retrofits)
- `mobile/package.json`, `mobile/app.json`, `mobile/eas.json`, `mobile/index.ts`
- New: `mobile/babel.config.js`
- `mobile/src/App.tsx`, `mobile/src/theme/AppThemeProvider.tsx`
- New: `mobile/src/components/ui/{MotionProvider,AnimatedCard,AnimatedListItem,PressableScale,HapticButton,Skeleton,SkeletonRow,AnimatedProgress,AnimatedNumber,ToastBanner,BottomSheet,SwipeRow,EmptyState}.tsx`
- 11 mobile screens (Tier 1/2/3 retrofits)
- Rewrite (preserve API): `mobile/src/components/{FadeInView,AnimatedOrbs}.tsx`

### Workstream 3
- New: `backend/tests/test_integration/{test_sms_typed_validation,test_review_resolve_dedup,test_reimport_signature,test_dlq_retry_flow,test_account_autopopulation,test_conversation_e2e}.py`
- New: `backend/tests/test_e2e/{conftest,test_real_folder_import,test_real_per_bank}.py`
- New: `backend/tests/test_parser/test_template_per_bank.py` + `_snapshot.py`
- Extend: `backend/tests/fixtures/generate_fixtures.py`
- New: `frontend/vitest.config.ts`, `frontend/playwright.config.ts`, `frontend/src/test/{setup.ts,msw/handlers.ts,fixtures/}`, `frontend/e2e/*.spec.ts`
- New: `mobile/jest.config.js`, `mobile/jest.setup.js`, `mobile/src/test/utils/renderWithProviders.tsx`, `mobile/.maestro/*.yaml`
- Modify: `.github/workflows/ci.yml`, `pyproject.toml` (markers), `Makefile` (e2e-real target)
- Update: `backend/TESTING.md`, `frontend/TESTING.md`, `mobile/TESTING.md`, `mobile/README.md`

---

# Verification plan

### Per-fix unit verification
- Run `cd backend && pytest -m "not e2e and not integration" -q` — all 182 existing tests + new bug-regression tests pass

### Integration verification
- `cd backend && pytest tests/test_integration -q` against Postgres testcontainer — bypass-path regressions caught

### E2E verification (the user's specific ask)
- Set `RUN_REAL_E2E=1` and `HISABCLUB_E2E_FOLDER=/home/ankit/Documents/FY24-25-Ankit-details`
- Run `cd backend && pytest tests/test_e2e -v` — full FY24-25 folder imports cleanly:
  - All 41 files discovered, 0 failures
  - Each bank's transactions extracted and validated
  - Tax compliance report produces non-zero income/TDS/interest
  - Per-bank snapshots match (or update with `RUN_REAL_E2E_UPDATE=1`)

### Frontend verification
- `cd frontend && npm test` — Vitest unit + component tests pass
- `cd frontend && npm run e2e` — Playwright onboarding/upload/statement-review/transactions specs pass against locally-running backend

### Mobile verification
- `cd mobile && npm test` — Jest unit + component tests pass
- `cd mobile && npm run e2e` — Maestro flows pass on Linux Android emulator
- Manual smoke: `expo run:ios` on Mac (or via EAS build) confirms iOS UX parity

### UI/UX verification (manual)
- Each Tier-1 page: skeleton → content transition smooth; stagger entrance visible; toasts on actions; modals replace native confirms
- Mobile: haptic feedback on key actions; swipe-row gestures work; iOS+Android both render identically

### Correctness verification
- Upload duplicate PDF → second instance dedup'd
- SMS that overlaps a PDF transaction (same amount/date/account/description) → DedupEngine merges, single canonical row
- Resolve a quarantined transaction whose amount/date/account already exists → `merged_count > 0`
- Tier 2/3 dedup with high-decimal-place amounts → exact match (no float drift)
- Balance walk on shuffled-date input → problem identifiers stable
- LLM chunk failure → `parse_errors["llm_chunks"]` populated, `Statement.warnings` mentions failed chunk indices
- Sanitizer: standalone 12-digit UPI ref preserved; 16-digit card with distant context still masked

---

# What this does NOT change

- llama.cpp runtime, model files, quantization, TurboQuant config
- `/home/ankit/Documents/local-llm/` shared LLM control plane
- Existing 6+ template parsers (HDFC/Axis/SBI CC+Savings, BOB savings, ICICI/Kotak stubs)
- Database schema beyond optional additive migrations (review_tasks nullable statement_id, plus column-default-only changes)
- Existing API contracts (all changes are additive: new fields, new endpoints)
- The `app/extraction/` module's authority over the statement parse path — Phase 3 strengthens it, doesn't replace it
- The Phase 2 plan at `/home/ankit/Documents/personal-finance-app/new-plan.md` — that file remains the feature-catalog source of truth
