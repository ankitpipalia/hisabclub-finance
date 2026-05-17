"""Validation helpers for extracted statement transactions."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.engines.parser.base import ExtractedTransaction

if TYPE_CHECKING:
    from app.engines.parser.base import ExtractedStatement


@dataclass(frozen=True)
class ValidationResult:
    transactions: list[ExtractedTransaction]
    warnings: list[str] = field(default_factory=list)
    dropped_count: int = 0
    review_required: bool = False
    details: dict[str, object] = field(default_factory=dict)


def validate_extracted_transactions(
    transactions: list[ExtractedTransaction],
    *,
    statement_period_start: date | None = None,
    statement_period_end: date | None = None,
) -> ValidationResult:
    valid: list[ExtractedTransaction] = []
    warnings: list[str] = []
    dropped = 0
    seen: set[tuple[str, int, str, str]] = set()

    lower_bound = statement_period_start - timedelta(days=120) if statement_period_start else None
    upper_bound = statement_period_end + timedelta(days=31) if statement_period_end else None

    for txn in transactions:
        description = " ".join((txn.description or "").split())
        if not description:
            dropped += 1
            continue
        if txn.amount is None or float(txn.amount) <= 0:
            dropped += 1
            continue
        if txn.direction not in {"debit", "credit"}:
            dropped += 1
            continue
        if lower_bound and txn.transaction_date < lower_bound:
            dropped += 1
            continue
        if upper_bound and txn.transaction_date > upper_bound:
            dropped += 1
            continue

        fingerprint = (
            txn.transaction_date.isoformat(),
            int(round(float(txn.amount) * 100)),
            txn.direction,
            description[:120].upper(),
        )
        if fingerprint in seen:
            dropped += 1
            continue
        seen.add(fingerprint)
        valid.append(
            ExtractedTransaction(
                transaction_date=txn.transaction_date,
                posting_date=txn.posting_date,
                description=description,
                amount=float(txn.amount),
                direction=txn.direction,
                reference_number=txn.reference_number,
                foreign_amount=txn.foreign_amount,
                foreign_currency=txn.foreign_currency,
                confidence=max(0.0, min(1.0, float(txn.confidence or 0.0))),
                line_number=txn.line_number,
            )
        )

    if dropped:
        warnings.append(
            f"Validation dropped {dropped} invalid or duplicate extracted transaction(s)."
        )

    return ValidationResult(transactions=valid, warnings=warnings, dropped_count=dropped)


def validate_extracted_statement(extracted: "ExtractedStatement") -> ValidationResult:
    txn_result = validate_extracted_transactions(
        extracted.transactions,
        statement_period_start=extracted.statement_period_start,
        statement_period_end=extracted.statement_period_end,
    )
    warnings = list(txn_result.warnings)
    details: dict[str, object] = {}
    review_required = False

    account_type = (extracted.account_type or "").strip().lower()
    if account_type in {"savings", "current"}:
        balance_walk = _build_balance_walk_validation(
            opening_balance=extracted.opening_balance,
            closing_balance=extracted.closing_balance,
            transactions=txn_result.transactions,
        )
        if balance_walk is not None:
            details["balance_walk"] = balance_walk
            if balance_walk.get("ok") is False:
                warnings.append(
                    "Balance walk mismatch detected for bank statement. Review required."
                )
                review_required = True
        else:
            details["balance_walk"] = {
                "applied": False,
                "reason": "opening_or_closing_balance_missing",
            }

    return ValidationResult(
        transactions=txn_result.transactions,
        warnings=warnings,
        dropped_count=txn_result.dropped_count,
        review_required=review_required,
        details=details,
    )


def _build_balance_walk_validation(
    *,
    opening_balance: float | None,
    closing_balance: float | None,
    transactions: list[ExtractedTransaction],
) -> dict[str, object] | None:
    if opening_balance is None or closing_balance is None:
        return None

    debit_total = round(
        sum(float(txn.amount) for txn in transactions if txn.direction == "debit"),
        2,
    )
    credit_total = round(
        sum(float(txn.amount) for txn in transactions if txn.direction == "credit"),
        2,
    )
    expected_closing_balance = round(float(opening_balance) + credit_total - debit_total, 2)
    actual_closing_balance = round(float(closing_balance), 2)
    gap = round(abs(actual_closing_balance - expected_closing_balance), 2)
    tolerance = Decimal("1.00")
    return {
        "applied": True,
        "opening_balance": round(float(opening_balance), 2),
        "closing_balance": actual_closing_balance,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "expected_closing_balance": expected_closing_balance,
        "gap": gap,
        "tolerance": float(tolerance),
        "ok": gap <= float(tolerance),
    }
