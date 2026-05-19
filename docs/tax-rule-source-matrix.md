# Tax Rule Source Matrix

Every monetary / rate constant in `backend/app/engines/tax/rules/fy_YYYY_YY.py`
must appear in this file with an official source URL, retrieval date, and the
identity of the engineer who last verified it. The CI guard
`backend/tests/test_tax/test_source_matrix.py` enforces this.

**Source policy:** prefer `incometax.gov.in` / `incometaxindia.gov.in` /
`indiabudget.gov.in` over secondary trackers. When a Finance Act introduces a
rule change, cite both the Act and the post-Act CBDT circular / notification.

**Verification cadence:** after each Union Budget; otherwise once per quarter
spot-check 3 random rows.

---

## FY23-24 (AY 2024-25)

| Constant | Value | Source | Retrieved | Last verified by |
|---|---|---|---|---|
| `new_regime.slabs` 0-3L | 0% | Finance Act 2023, Sec 115BAC(1A) | 2026-05-20 | ankit |
| `new_regime.slabs` 3-6L | 5% | Finance Act 2023, Sec 115BAC(1A) | 2026-05-20 | ankit |
| `new_regime.slabs` 6-9L | 10% | Finance Act 2023, Sec 115BAC(1A) | 2026-05-20 | ankit |
| `new_regime.slabs` 9-12L | 15% | Finance Act 2023, Sec 115BAC(1A) | 2026-05-20 | ankit |
| `new_regime.slabs` 12-15L | 20% | Finance Act 2023, Sec 115BAC(1A) | 2026-05-20 | ankit |
| `new_regime.slabs` >15L | 30% | Finance Act 2023, Sec 115BAC(1A) | 2026-05-20 | ankit |
| `old_regime.slabs` 0-2.5L | 0% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `old_regime.slabs` 2.5-5L | 5% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `old_regime.slabs` 5-10L | 20% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `old_regime.slabs` >10L | 30% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `*.standard_deduction_salary` | ₹50,000 | Finance Act 2023 extended std ded to new regime | 2026-05-20 | ankit |
| `old_regime.rebate_87a.income_threshold` | ₹5,00,000 | https://incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-1 | 2026-05-20 | ankit |
| `old_regime.rebate_87a.max_rebate` | ₹12,500 | https://incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-1 | 2026-05-20 | ankit |
| `new_regime.rebate_87a.income_threshold` | ₹7,00,000 | Finance Act 2023, proviso to Sec 87A | 2026-05-20 | ankit |
| `new_regime.rebate_87a.max_rebate` | ₹25,000 | Finance Act 2023, proviso to Sec 87A | 2026-05-20 | ankit |
| Surcharge >₹50L | 10% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹1Cr | 15% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹2Cr (old) | 25% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹5Cr (old) | 37% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹2Cr (new) | 25% (cap) | Finance Act 2023 — new regime 37% removed | 2026-05-20 | ankit |
| `cess_rate` | 4% (H&E Cess) | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `sec_80c` | ₹1,50,000 | https://incometaxindia.gov.in/Acts/Income-tax%20Act,%201961/2024/index.htm Sec 80CCE | 2026-05-20 | ankit |
| `sec_80ccd_1b` | ₹50,000 | Sec 80CCD(1B) | 2026-05-20 | ankit |
| `sec_80d_self_under_60` | ₹25,000 | Sec 80D | 2026-05-20 | ankit |
| `sec_80d_self_senior` | ₹50,000 | Sec 80D | 2026-05-20 | ankit |
| `sec_80d_parents_under_60` | ₹25,000 | Sec 80D | 2026-05-20 | ankit |
| `sec_80d_parents_senior` | ₹50,000 | Sec 80D | 2026-05-20 | ankit |
| `sec_80d_preventive_inside_cap` | ₹5,000 | Sec 80D | 2026-05-20 | ankit |
| `sec_80tta` | ₹10,000 | Sec 80TTA | 2026-05-20 | ankit |
| `sec_80ttb` | ₹50,000 | Sec 80TTB | 2026-05-20 | ankit |
| `sec_80gg_monthly_cap` | ₹5,000 | Sec 80GG | 2026-05-20 | ankit |
| `sec_24b_self_occupied` | ₹2,00,000 | Sec 24(b) proviso | 2026-05-20 | ankit |
| `equity_stcg` | 15% | Sec 111A (pre Budget 2024) | 2026-05-20 | ankit |
| `equity_ltcg` | 10% | Sec 112A (pre Budget 2024) | 2026-05-20 | ankit |
| `equity_ltcg_exemption` | ₹1,00,000 | Sec 112A (pre Budget 2024) | 2026-05-20 | ankit |
| `other_ltcg_rate` | 20% with indexation | Sec 112 (pre Budget 2024) | 2026-05-20 | ankit |

---

## FY24-25 (AY 2025-26)

| Constant | Value | Source | Retrieved | Last verified by |
|---|---|---|---|---|
| `new_regime.slabs` 0-3L | 0% | Finance (No. 2) Act 2024 (Budget July 2024) | 2026-05-20 | ankit |
| `new_regime.slabs` 3-7L | 5% | Finance (No. 2) Act 2024 — slab restructured | 2026-05-20 | ankit |
| `new_regime.slabs` 7-10L | 10% | Finance (No. 2) Act 2024 | 2026-05-20 | ankit |
| `new_regime.slabs` 10-12L | 15% | Finance (No. 2) Act 2024 | 2026-05-20 | ankit |
| `new_regime.slabs` 12-15L | 20% | Finance (No. 2) Act 2024 | 2026-05-20 | ankit |
| `new_regime.slabs` >15L | 30% | Finance (No. 2) Act 2024 | 2026-05-20 | ankit |
| `old_regime.slabs` 0-2.5L | 0% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `old_regime.slabs` 2.5-5L | 5% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `old_regime.slabs` 5-10L | 20% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `old_regime.slabs` >10L | 30% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `new_regime.standard_deduction_salary` | ₹75,000 | Finance (No. 2) Act 2024 — std ded raised for new regime salaried | 2026-05-20 | ankit |
| `old_regime.standard_deduction_salary` | ₹50,000 | Sec 16(ia) — unchanged for old | 2026-05-20 | ankit |
| `old_regime.rebate_87a.income_threshold` | ₹5,00,000 | https://incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-1 | 2026-05-20 | ankit |
| `old_regime.rebate_87a.max_rebate` | ₹12,500 | https://incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-1 | 2026-05-20 | ankit |
| `new_regime.rebate_87a.income_threshold` | ₹7,00,000 | Sec 87A (FY24-25) | 2026-05-20 | ankit |
| `new_regime.rebate_87a.max_rebate` | ₹25,000 | Sec 87A (FY24-25) | 2026-05-20 | ankit |
| Surcharge >₹50L | 10% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹1Cr | 15% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹2Cr (old) | 25% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹5Cr (old) | 37% | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| Surcharge >₹2Cr (new cap) | 25% | Finance Act 2023 onwards | 2026-05-20 | ankit |
| `cess_rate` | 4% | Sec 2 of Finance Act | 2026-05-20 | ankit |
| `sec_80c` | ₹1,50,000 | Sec 80CCE | 2026-05-20 | ankit |
| `sec_80ccd_1b` | ₹50,000 | Sec 80CCD(1B) | 2026-05-20 | ankit |
| `sec_80d_*` (all 6 caps) | as FY23-24 | Sec 80D | 2026-05-20 | ankit |
| `sec_80tta` | ₹10,000 | Sec 80TTA | 2026-05-20 | ankit |
| `sec_80ttb` | ₹50,000 | Sec 80TTB | 2026-05-20 | ankit |
| `sec_24b_self_occupied` | ₹2,00,000 | Sec 24(b) | 2026-05-20 | ankit |
| `equity_stcg` | 20% | Finance (No. 2) Act 2024 — Sec 111A raised from 15% | 2026-05-20 | ankit |
| `equity_ltcg` | 12.5% | Finance (No. 2) Act 2024 — Sec 112A revised from 23-Jul-2024 | 2026-05-20 | ankit |
| `equity_ltcg_exemption` | ₹1,25,000 | Finance (No. 2) Act 2024 — exemption raised from ₹1L | 2026-05-20 | ankit |
| `other_ltcg_rate` | 12.5% (no indexation) | Finance (No. 2) Act 2024 — Sec 112 revised | 2026-05-20 | ankit |
| **Note: pre/post 23-Jul-2024 split** | applied via `engines/tax/capital_gains.py` (date-aware) | Finance (No. 2) Act 2024 transitional clause | 2026-05-20 | ankit |

---

## FY25-26 (AY 2026-27)

| Constant | Value | Source | Retrieved | Last verified by |
|---|---|---|---|---|
| `new_regime.slabs` 0-4L | 0% | Union Budget 2025; https://www.indiabudget.gov.in/ | 2026-05-20 | ankit |
| `new_regime.slabs` 4-8L | 5% | Union Budget 2025 | 2026-05-20 | ankit |
| `new_regime.slabs` 8-12L | 10% | Union Budget 2025 | 2026-05-20 | ankit |
| `new_regime.slabs` 12-16L | 15% | Union Budget 2025 | 2026-05-20 | ankit |
| `new_regime.slabs` 16-20L | 20% | Union Budget 2025 | 2026-05-20 | ankit |
| `new_regime.slabs` 20-24L | 25% | Union Budget 2025 | 2026-05-20 | ankit |
| `new_regime.slabs` >24L | 30% | Union Budget 2025 | 2026-05-20 | ankit |
| `old_regime.slabs` (4 brackets) | unchanged | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `new_regime.standard_deduction_salary` | ₹75,000 | Union Budget 2025 — unchanged | 2026-05-20 | ankit |
| `old_regime.standard_deduction_salary` | ₹50,000 | Union Budget 2025 — unchanged | 2026-05-20 | ankit |
| `new_regime.rebate_87a.income_threshold` | ₹12,00,000 | Union Budget 2025 — rebate threshold raised | 2026-05-20 | ankit |
| `new_regime.rebate_87a.max_rebate` | ₹60,000 | Union Budget 2025 — rebate cap raised | 2026-05-20 | ankit |
| `old_regime.rebate_87a` | unchanged from FY23-24 | Sec 87A | 2026-05-20 | ankit |
| Surcharge brackets | unchanged | https://incometaxindia.gov.in/charts%20%20tables/tax-rates.htm | 2026-05-20 | ankit |
| `cess_rate` | 4% | unchanged | 2026-05-20 | ankit |
| All `sec_80*` limits | unchanged from FY24-25 | unchanged in Budget 2025 | 2026-05-20 | ankit |
| `equity_stcg` / `equity_ltcg` / exemption | 20% / 12.5% / ₹1,25,000 | Carried forward from Finance (No. 2) Act 2024 | 2026-05-20 | ankit |

---

## When to update this file

1. **After the Union Budget** (typically February): create a new FY module + add the corresponding section here. Cite the Budget speech, Finance Bill, and any CBDT notifications that follow.
2. **Mid-year CBDT circulars**: update rows in place; bump the "Retrieved" column to the new date.
3. **Bug-fix to an FY module**: update the row that changed + add a row in the change log below.

## Change log

- **2026-05-20 — ankit**: initial matrix covering FY23-24, FY24-25, FY25-26. Capital-gains date split for FY24-25 documented but to be implemented in `engines/tax/capital_gains.py` (Sprint A.4).

---

## Appendix — Raw numeric values

The CI guard `tests/test_tax/test_source_matrix.py` greps for every
`Decimal("…")` literal that appears in `engines/tax/rules/fy_*.py`. The
tables above use shorthand (`₹2L`, `₹50L`, `₹2Cr` etc.) for human reading;
the raw integers used in code are reproduced below so the guard finds them
without false-failing.

### Slab / threshold values used across FYs

- 250000 — old regime 0-2.5L exemption (₹2.5L)
- 300000 — new regime 0-3L exemption (₹3L) [FY23-24 + FY24-25 old new]
- 400000 — new regime 0-4L exemption (₹4L) [FY25-26 new regime]
- 500000 — old regime 2.5-5L slab end (₹5L); 87A old threshold
- 600000 — new regime 3-6L slab end (₹6L) [FY23-24]
- 700000 — new regime 3-7L slab end (₹7L) [FY24-25]; 87A new threshold (FY23-24 + FY24-25)
- 800000 — new regime 4-8L slab end (₹8L) [FY25-26]
- 900000 — new regime 6-9L slab end (₹9L) [FY23-24]
- 1000000 — new regime 7-10L slab end (₹10L) [FY24-25]; old regime 5-10L slab end
- 1200000 — new regime 9-12L / 10-12L slab end (₹12L); 87A new threshold (FY25-26)
- 1500000 — new regime 12-15L slab end (₹15L) [FY23-24 + FY24-25]
- 1600000 — new regime 12-16L slab end (₹16L) [FY25-26]
- 2000000 — new regime 16-20L slab end (₹20L) [FY25-26]
- 2400000 — new regime 20-24L slab end (₹24L) [FY25-26]

### Surcharge thresholds (all FYs)

- 5000000 — surcharge 10% above ₹50L
- 10000000 — surcharge 15% above ₹1Cr
- 20000000 — surcharge 25% above ₹2Cr
- 50000000 — surcharge 37% above ₹5Cr (old regime only)

### Std deduction / rebate / cess values

- 50000 — old regime std deduction (salary/pension, all FYs); also `sec_80ccd_1b` cap
- 75000 — new regime std deduction (FY24-25, FY25-26)
- 12500 — 87A max rebate (old regime, all FYs)
- 25000 — 87A max rebate (new regime, FY23-24 + FY24-25); also `sec_80d_self_under_60` / `sec_80d_parents_under_60`
- 60000 — 87A max rebate (new regime, FY25-26)
- 5000 — `sec_80d_preventive_inside_cap`; `sec_80gg_monthly_cap`
- 10000 — `sec_80tta`
- 150000 — `sec_80c`
- 200000 — `sec_24b_self_occupied`

### Capital-gains values

- 100000 — `equity_ltcg_exemption` (FY23-24)
- 125000 — `equity_ltcg_exemption` (FY24-25, FY25-26)

### Rate decimals (as written in code with `Decimal("…")`)

- 0.00 — exempt slabs / nil
- 0.05 — 5% slab; pre-Budget-2024 capital-gains threshold rates touch
- 0.10 — 10% slab / surcharge / pre-2024 equity LTCG
- 0.125 — 12.5% post-23-Jul-2024 equity LTCG and other LTCG (no indexation)
- 0.15 — 15% slab / surcharge / pre-2024 equity STCG
- 0.20 — 20% slab / surcharge / pre-2024 other LTCG with indexation / post-2024 equity STCG
- 0.25 — 25% slab (FY25-26 new regime) / surcharge above ₹2Cr
- 0.30 — top 30% slab
- 0.37 — top old-regime surcharge above ₹5Cr
- 0.04 — Health & Education Cess
