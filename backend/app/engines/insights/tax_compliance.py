from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.document_artifact import DocumentArtifact
from app.models.statement import Statement

_CASH_KEYWORDS = ("ATM", "CASH", "WITHDRAWAL")
_TAX_DOC_TYPES = (
    "tax_form",
    "tax_challan",
    "interest_certificate",
    "demat_tax_report",
    "dividend_report",
    "fd_report",
    "ppf_statement",
)

_NEW_REGIME_CONFIG_BY_FY_START = {
    # FY 2025-26 onwards (AY 2026-27 onwards)
    2025: {
        "slabs": (
            (4_00_000, 0.00),
            (8_00_000, 0.05),
            (12_00_000, 0.10),
            (16_00_000, 0.15),
            (20_00_000, 0.20),
            (24_00_000, 0.25),
            (float("inf"), 0.30),
        ),
        "rebate_threshold": 12_00_000,
        "max_rebate": 60_000,
    },
    # FY 2024-25 (AY 2025-26)
    2024: {
        "slabs": (
            (3_00_000, 0.00),
            (7_00_000, 0.05),
            (10_00_000, 0.10),
            (12_00_000, 0.15),
            (15_00_000, 0.20),
            (float("inf"), 0.30),
        ),
        "rebate_threshold": 7_00_000,
        "max_rebate": 25_000,
    },
    # FY 2023-24 and before under 115BAC default structure
    2023: {
        "slabs": (
            (3_00_000, 0.00),
            (6_00_000, 0.05),
            (9_00_000, 0.10),
            (12_00_000, 0.15),
            (15_00_000, 0.20),
            (float("inf"), 0.30),
        ),
        "rebate_threshold": 7_00_000,
        "max_rebate": 25_000,
    },
}


def build_tax_action_items(
    totals: dict[str, float],
    coverage: dict[str, int],
    unresolved_statement_docs: int,
    high_value_cash_expense_count: int,
    *,
    savings_account_count: int | None = None,
    documented_interest_income: float | None = None,
    documented_tax_payments: float | None = None,
) -> list[dict]:
    items: list[dict] = []
    if coverage.get("tax_form", 0) == 0:
        items.append(
            {
                "severity": "warning",
                "title": "Missing Tax Forms",
                "detail": "No Form-16/Form-12BB style documents are currently registered.",
            }
        )
    if totals.get("interest_income", 0.0) > 0 and coverage.get("interest_certificate", 0) == 0:
        items.append(
            {
                "severity": "warning",
                "title": "Interest Income Without Certificate",
                "detail": (
                    "Interest income exists in ledger but no interest/TDS certificate "
                    "is registered."
                ),
            }
        )
    if totals.get("dividend_income", 0.0) > 0 and coverage.get("dividend_report", 0) == 0:
        items.append(
            {
                "severity": "warning",
                "title": "Dividend Income Without Report",
                "detail": "Dividend income detected but no dividend report document is registered.",
            }
        )
    if totals.get("tax_payments", 0.0) > 0 and coverage.get("tax_challan", 0) == 0:
        items.append(
            {
                "severity": "warning",
                "title": "Tax Payments Without Challan",
                "detail": "Tax outflows are present but no challan receipt was detected.",
            }
        )
    if totals.get("other_income", 0.0) >= 50000:
        items.append(
            {
                "severity": "info",
                "title": "Review Other Income",
                "detail": (
                    "Other income exceeds INR 50,000. Cross-check with AIS/26AS "
                    "before filing."
                ),
            }
        )
    if high_value_cash_expense_count > 0:
        items.append(
            {
                "severity": "warning",
                "title": "High-Value Cash Transactions",
                "detail": (
                    f"{high_value_cash_expense_count} high-value cash-like expenses "
                    "need audit tagging."
                ),
            }
        )
    if savings_account_count is not None and savings_account_count == 0:
        items.append(
            {
                "severity": "warning",
                "title": "No Savings Statements Linked",
                "detail": (
                    "No savings/current account statements were detected. "
                    "Upload at least one bank account statement for accurate tax mapping."
                ),
            }
        )
    if documented_interest_income is not None and totals.get("interest_income", 0.0) > 0:
        gap = abs(totals.get("interest_income", 0.0) - documented_interest_income)
        if gap >= 5000:
            items.append(
                {
                    "severity": "warning",
                    "title": "Interest Income Mismatch",
                    "detail": (
                        "Ledger interest and uploaded certificates differ materially. "
                        f"Current gap is INR {gap:,.0f}."
                    ),
                }
            )
    if documented_tax_payments is not None and totals.get("tax_payments", 0.0) > 0:
        gap = abs(totals.get("tax_payments", 0.0) - documented_tax_payments)
        if gap >= 1000:
            items.append(
                {
                    "severity": "warning",
                    "title": "Tax Payment Documentation Gap",
                    "detail": (
                        "Ledger tax payments and challan documents are not fully aligned. "
                        f"Current gap is INR {gap:,.0f}."
                    ),
                }
            )
    if unresolved_statement_docs > 0:
        items.append(
            {
                "severity": "info",
                "title": "Unresolved Statement Parsers",
                "detail": (
                    f"{unresolved_statement_docs} statement documents need parser "
                    "support review."
                ),
            }
        )

    if not items:
        items.append(
            {
                "severity": "ok",
                "title": "No Immediate Tax Flags",
                "detail": (
                    "Current document coverage and ledger signals look consistent for "
                    "this period."
                ),
            }
        )
    return items


def _financial_year_start_for(period_start: date) -> int:
    return period_start.year if period_start.month >= 4 else period_start.year - 1


def _new_regime_config_for_fy_start(fy_start_year: int) -> dict:
    if fy_start_year >= 2025:
        return _NEW_REGIME_CONFIG_BY_FY_START[2025]
    if fy_start_year == 2024:
        return _NEW_REGIME_CONFIG_BY_FY_START[2024]
    return _NEW_REGIME_CONFIG_BY_FY_START[2023]


def _calculate_new_regime_tax(
    estimated_taxable_income: float,
    fy_start_year: int,
) -> dict[str, float]:
    config = _new_regime_config_for_fy_start(fy_start_year)
    slabs: tuple[tuple[float, float], ...] = config["slabs"]
    rebate_threshold = float(config["rebate_threshold"])
    max_rebate = float(config["max_rebate"])

    income = max(0.0, float(estimated_taxable_income))
    prev_limit = 0.0
    base_tax = 0.0

    for upper_limit, rate in slabs:
        if income <= prev_limit:
            break
        taxable_in_slab = min(income, upper_limit) - prev_limit
        if taxable_in_slab > 0:
            base_tax += taxable_in_slab * float(rate)
        prev_limit = upper_limit

    rebate = 0.0
    if income <= rebate_threshold:
        rebate = min(base_tax, max_rebate)
    elif income <= rebate_threshold + max_rebate:
        # Marginal relief around rebate cut-off.
        allowed_tax = income - rebate_threshold
        rebate = max(0.0, min(max_rebate, base_tax - allowed_tax))

    tax_after_rebate = max(0.0, base_tax - rebate)
    cess = tax_after_rebate * 0.04
    total_liability = tax_after_rebate + cess

    return {
        "new_regime_tax_before_rebate": round(base_tax, 2),
        "new_regime_rebate": round(rebate, 2),
        "new_regime_tax_after_rebate": round(tax_after_rebate, 2),
        "new_regime_cess": round(cess, 2),
        "new_regime_total_tax": round(total_liability, 2),
        "new_regime_rebate_threshold": round(rebate_threshold, 2),
    }


def _to_float(value: object | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _account_key(bank_name: str | None, account_masked: str | None) -> tuple[str, str]:
    bank = (bank_name or "UNKNOWN").strip().upper()
    account = (account_masked or "UNKNOWN").strip().upper()
    return bank, account


def _build_linkage_check(
    *,
    check: str,
    ledger_amount: float,
    document_amount: float,
    threshold: float,
    detail: str,
) -> dict:
    gap = round(ledger_amount - document_amount, 2)
    abs_gap = abs(gap)
    if ledger_amount == 0 and document_amount == 0:
        status = "no_data"
    elif abs_gap <= threshold:
        status = "matched"
    else:
        status = "review_required"
    return {
        "check": check,
        "status": status,
        "ledger_amount": round(ledger_amount, 2),
        "document_amount": round(document_amount, 2),
        "gap": gap,
        "detail": detail,
    }


async def build_tax_compliance_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> dict:
    fy_start_year = _financial_year_start_for(period_start)
    fy_label = f"FY {fy_start_year}-{(fy_start_year + 1) % 100:02d}"

    rows = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(CanonicalTransaction.user_id == user_id)
            .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
            .where(CanonicalTransaction.transaction_date >= period_start)
            .where(CanonicalTransaction.transaction_date <= period_end)
        )
    ).all()

    totals = {
        "total_income": 0.0,
        "salary_income": 0.0,
        "interest_income": 0.0,
        "dividend_income": 0.0,
        "other_income": 0.0,
        "total_expense": 0.0,
        "tax_payments": 0.0,
        "investment_outflow": 0.0,
        "transfer_internal": 0.0,
        "new_regime_tax_before_rebate": 0.0,
        "new_regime_rebate": 0.0,
        "new_regime_tax_after_rebate": 0.0,
        "new_regime_cess": 0.0,
        "new_regime_total_tax": 0.0,
        "new_regime_rebate_threshold": 0.0,
        "tax_due_or_refund": 0.0,
        "documented_interest_income": 0.0,
        "documented_interest_tds": 0.0,
        "documented_tax_payments": 0.0,
        "documented_fd_principal": 0.0,
        "documented_fd_interest": 0.0,
        "documented_ppf_contribution": 0.0,
        "documented_ppf_interest": 0.0,
        "documented_ppf_closing_balance": 0.0,
        "savings_account_count": 0.0,
    }
    high_value_cash_expenses: list[dict] = []
    interest_income_by_account: dict[tuple[str, str], float] = {}

    for txn, _category_name in rows:
        amount = float(txn.amount)
        nature = (txn.transaction_nature or "").lower()
        merchant = (txn.merchant_raw or "").upper()

        if nature in {"income", "interest_income", "dividend_income"}:
            totals["total_income"] += amount
            if nature == "interest_income":
                totals["interest_income"] += amount
                if (txn.account_type or "").lower() in {"savings", "current", "bank_account"}:
                    key = _account_key(txn.bank_name, txn.account_masked)
                    interest_income_by_account[key] = (
                        interest_income_by_account.get(key, 0.0) + amount
                    )
            elif nature == "dividend_income":
                totals["dividend_income"] += amount
            elif "SALARY" in merchant or "PAYROLL" in merchant:
                totals["salary_income"] += amount
            else:
                totals["other_income"] += amount
        elif nature == "expense":
            totals["total_expense"] += amount
        elif nature == "tax":
            totals["tax_payments"] += amount
        elif nature == "investment":
            totals["investment_outflow"] += amount
        elif nature == "transfer_internal":
            totals["transfer_internal"] += amount

        if (
            txn.direction == "debit"
            and amount >= 10000
            and any(k in merchant for k in _CASH_KEYWORDS)
        ):
            high_value_cash_expenses.append(
                {
                    "transaction_id": str(txn.id),
                    "transaction_date": txn.transaction_date,
                    "amount": round(amount, 2),
                    "merchant_raw": txn.merchant_raw,
                    "bank_name": txn.bank_name,
                    "account_type": txn.account_type,
                }
            )

    coverage_rows = (
        await db.execute(
            select(DocumentArtifact.doc_type, func.count(DocumentArtifact.id))
            .where(DocumentArtifact.user_id == user_id)
            .where(DocumentArtifact.doc_type.in_(_TAX_DOC_TYPES))
            .group_by(DocumentArtifact.doc_type)
        )
    ).all()
    coverage = {doc_type: int(count) for doc_type, count in coverage_rows}
    for doc_type in _TAX_DOC_TYPES:
        coverage.setdefault(doc_type, 0)

    savings_account_rows = (
        await db.execute(
            select(
                Statement.bank_name,
                Statement.account_number_masked,
                func.count(Statement.id).label("statement_count"),
            )
            .where(Statement.user_id == user_id)
            .where(Statement.account_type.in_(("savings", "current")))
            .group_by(Statement.bank_name, Statement.account_number_masked)
        )
    ).all()
    savings_accounts: list[dict] = []
    seen_account_keys: set[tuple[str, str]] = set()
    for bank_name, account_masked, statement_count in savings_account_rows:
        key = _account_key(bank_name, account_masked)
        seen_account_keys.add(key)
        savings_accounts.append(
            {
                "bank_name": bank_name or "UNKNOWN",
                "account_masked": account_masked,
                "statement_count": int(statement_count or 0),
                "interest_income": round(interest_income_by_account.get(key, 0.0), 2),
            }
        )
    for key, interest_amount in interest_income_by_account.items():
        if key in seen_account_keys:
            continue
        savings_accounts.append(
            {
                "bank_name": key[0],
                "account_masked": None if key[1] == "UNKNOWN" else key[1],
                "statement_count": 0,
                "interest_income": round(interest_amount, 2),
            }
        )
    savings_accounts.sort(
        key=lambda item: (
            item["bank_name"] or "",
            item["account_masked"] or "",
        )
    )
    totals["savings_account_count"] = float(len(savings_accounts))

    artifact_rows = (
        await db.execute(
            select(DocumentArtifact)
            .where(DocumentArtifact.user_id == user_id)
            .where(DocumentArtifact.doc_type.in_(_TAX_DOC_TYPES))
            .where(DocumentArtifact.status.in_(("parsed", "skipped", "discovered")))
        )
    ).scalars().all()
    challan_count = 0
    for artifact in artifact_rows:
        metadata = artifact.metadata_json or {}
        doc_type = (artifact.doc_type or "").lower()
        if doc_type == "interest_certificate":
            totals["documented_interest_income"] += _to_float(metadata.get("interest_amount"))
            totals["documented_interest_tds"] += _to_float(metadata.get("tds_amount"))
        elif doc_type == "fd_report":
            totals["documented_fd_principal"] += _to_float(metadata.get("principal_total"))
            totals["documented_fd_interest"] += _to_float(metadata.get("interest_total"))
        elif doc_type == "tax_challan":
            amount = _to_float(metadata.get("tax_paid_amount"))
            if amount > 0:
                challan_count += 1
            totals["documented_tax_payments"] += amount
        elif doc_type == "ppf_statement":
            totals["documented_ppf_contribution"] += _to_float(metadata.get("contribution_amount"))
            totals["documented_ppf_interest"] += _to_float(metadata.get("interest_amount"))
            totals["documented_ppf_closing_balance"] += _to_float(metadata.get("closing_balance"))

    unresolved_statement_docs = int(
        (
            await db.execute(
                select(func.count(DocumentArtifact.id))
                .where(DocumentArtifact.user_id == user_id)
                .where(DocumentArtifact.doc_type.in_(("bank_statement", "credit_card_statement")))
                .where(
                    (DocumentArtifact.status == "failed")
                    | (
                        (DocumentArtifact.status == "skipped")
                        & (
                            DocumentArtifact.parse_message.ilike("%No parser configured%")
                            | DocumentArtifact.parse_message.ilike(
                                "%Could not identify the bank/statement type%"
                            )
                        )
                    )
                )
            )
        ).scalar()
        or 0
    )

    totals["estimated_taxable_income"] = round(
        totals["salary_income"]
        + totals["interest_income"]
        + totals["dividend_income"]
        + totals["other_income"],
        2,
    )
    tax_calc = _calculate_new_regime_tax(
        estimated_taxable_income=totals["estimated_taxable_income"],
        fy_start_year=fy_start_year,
    )
    totals.update(tax_calc)
    totals["tax_due_or_refund"] = round(
        totals["new_regime_total_tax"] - totals["tax_payments"],
        2,
    )

    for key in list(totals.keys()):
        totals[key] = round(totals[key], 2)

    linkage_checks = [
        _build_linkage_check(
            check="interest_income_vs_certificates",
            ledger_amount=totals["interest_income"],
            document_amount=totals["documented_interest_income"],
            threshold=500.0,
            detail="Compares ledger interest credits against uploaded interest/PPF/FD evidence.",
        ),
        _build_linkage_check(
            check="tax_payments_vs_challans",
            ledger_amount=totals["tax_payments"],
            document_amount=totals["documented_tax_payments"],
            threshold=500.0,
            detail="Compares ledger tax outflows against income-tax challans and acknowledgements.",
        ),
        _build_linkage_check(
            check="investment_outflow_vs_ppf_fd",
            ledger_amount=totals["investment_outflow"],
            document_amount=(
                totals["documented_fd_principal"] + totals["documented_ppf_contribution"]
            ),
            threshold=2000.0,
            detail="Compares investment debits against FD principal and PPF contributions.",
        ),
    ]

    high_value_cash_expenses.sort(key=lambda x: x["amount"], reverse=True)
    action_items = build_tax_action_items(
        totals=totals,
        coverage=coverage,
        unresolved_statement_docs=unresolved_statement_docs,
        high_value_cash_expense_count=len(high_value_cash_expenses),
        savings_account_count=int(totals["savings_account_count"]),
        documented_interest_income=totals["documented_interest_income"],
        documented_tax_payments=totals["documented_tax_payments"],
    )

    return {
        "period_start": period_start,
        "period_end": period_end,
        "tax_regime": "new",
        "tax_financial_year": fy_label,
        "totals": totals,
        "document_coverage": coverage,
        "unresolved_statement_docs": unresolved_statement_docs,
        "high_value_cash_expenses": high_value_cash_expenses[:20],
        "savings_accounts": savings_accounts,
        "linkage_checks": linkage_checks,
        "document_amounts": {
            "interest_income": totals["documented_interest_income"],
            "interest_tds": totals["documented_interest_tds"],
            "tax_payments": totals["documented_tax_payments"],
            "fd_principal": totals["documented_fd_principal"],
            "fd_interest": totals["documented_fd_interest"],
            "ppf_contribution": totals["documented_ppf_contribution"],
            "ppf_interest": totals["documented_ppf_interest"],
            "ppf_closing_balance": totals["documented_ppf_closing_balance"],
            "challan_count": float(challan_count),
        },
        "action_items": action_items,
        "tax_notes": [
            f"Computed using India new tax regime slabs for {fy_label}.",
            "Health & Education cess at 4% is included.",
            (
                "Surcharge and salary standard deduction adjustments are not applied "
                "in this estimate."
            ),
            (
                "Document linkage uses uploaded metadata from interest certificates, "
                "FD reports, tax challans, and PPF statements."
            ),
        ],
    }
