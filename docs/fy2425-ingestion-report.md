# FY24-25 Ingestion Report
Date: 2026-04-27

Target folder: `/home/ankit/Documents/FY24-25-Ankit-details`

Raw local artifacts:

- Inventory: `/tmp/fy2425_inventory.txt`
- Probe report: `/tmp/fy2425_probe_report.json`
- Probe output: `/tmp/fy2425_probe_output.txt`
- Phase 4 DB summary: `/tmp/fy2425_phase4_db_summary.txt`

Validation:

- `ruff check` on touched backend parser/promoter/test files: passed
- `pytest tests/ -q --tb=short`: 193 passed, 4 warnings

## Folder Inventory

- Total files: 41
- PDFs: 29
- Non-PDF files: 12 `.xlsx`
- Readable PDFs: 27
- Encrypted PDFs requiring password: 2
- Image-only PDFs requiring OCR: 0
- PDF extraction errors after encryption check: 0

The two files previously reported as `PdfminerException` are encrypted. `pdfplumber` fails, `pypdf` reports the files are not decrypted, and `pikepdf` raises `PasswordError`. They should be handled through password-required upload flow, not through a text-extraction fallback.

Encrypted/password-required files:

- `Demat/Groww/Groww_Balance_Statement_9107616824_01-04-2024_31-03-2025.pdf`
- `Demat/Groww/Mutual_Funds_ELSS_Statement_01-04-2024_31-03-2025.pdf`

No password values are committed.

## Phase 4 Fixes

### BOB Savings Parser

Implemented deterministic template parser `bob_savings_v1` for the real BOB statement layout:

```text
TRAN DATE | VALUE DATE | NARRATION | CHQ.NO. | WITHDRAWAL(DR) | DEPOSIT(CR) | BALANCE(INR)
```

Key behavior:

- No LLM dependency for BOB savings statements.
- Direction is inferred deterministically from balance deltas and the DR/CR table layout.
- Opening balance is inferred from the first chronological transaction when the PDF has no explicit opening-balance line.
- Closing balance is taken from the last chronological row.
- Statement period is extracted from the header.
- All promoted rows use `extraction_source=template`.

Local Phase 4 reimport result for the Phase 3 test user:

```text
bank_name=BOB
parser_used=bob_savings_v1
parse_status=parsed
period=2024-04-01..2025-03-31
opening_balance=8307.49
closing_balance=10406.41
promoted=13
reviews=0
balance_walk_passed=True
sources=['template']
```

### Review Gate Adjustment

The generic `large_amount` review trigger was too noisy for high-confidence template rows with a passing balance walk. It now still applies to AI-sourced or unverified rows, but not to deterministic template rows whose balance walk passed.

This preserves the safety gate where extraction quality is uncertain while avoiding review backlog for known-bank template statements.

### HDFC Credit Card Period

The HDFC CC parser now extracts period metadata when available and uses a statement-date fallback. If the document contains transactions outside that fallback window, the parser expands the period to include the actual transaction date range. This avoids invalidating rows in multi-month HDFC exports.

Local Phase 4 reimport result:

```text
bank_name=HDFC
parser_used=hdfc_cc_v1
parse_status=parsed
period=2024-11-17..2025-03-15
promoted=68
reviews=0
sources=['template']
```

### Duplicate Cleanup

For the Phase 3 test user, the old BOB rows were removed and reimported cleanly:

- Deleted old review-required BOB import: 13 canonical rows, 13 parsed rows, 13 review tasks.
- Deleted old duplicate BOB reimport: 1 canonical row, 1 parsed row, 1 review task.
- Reimported BOB with `bob_savings_v1`: 13 canonical rows, 0 review tasks.

A rolled-back duplicate simulation of the same BOB file reported:

```text
promoted=0
duplicates=13
in_review=0
```

The rollback kept the live DB with one active clean BOB statement.

## Current Phase 4 DB State

For the Phase 3 test user:

```text
BOB  savings      bob_savings_v1  parsed  txns=13  reviews=0  balance_walk=True   source=template
HDFC credit_card  hdfc_cc_v1      parsed  txns=68  reviews=0  balance_walk=N/A    source=template
```

Audit coverage:

```text
canonical_rows=81
dedup_keys=81
evidence_rows=81
```

Open review backlog for these Phase 4 imports: none.

## Remaining Product Gaps

- ICICI savings full template parser is still missing.
- Kotak savings and Kotak credit-card full template parsers are still missing.
- XLSX investment/broker statements are still registered/classified only; no spreadsheet ledger parser exists yet.
- The two encrypted Groww PDFs require user-provided passwords before ingestion.
- The running system service on `:8356` could not be restarted from this shell because systemd required interactive authentication. Phase 4 verification used the current code path directly against the local DB with `LLM_ENABLED=false`; restart the backend service before relying on HTTP uploads to use these exact parser changes.
