from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.config import settings
from app.engines.parser.amount_utils import parse_indian_date
from app.extraction.models import (
    BalanceWalkProblem,
    BalanceWalkResult,
    RawTransaction,
    StatementPeriod,
    ValidatedTransaction,
    ValidationStatus,
)

_SPACE_RE = re.compile(r"\s+")
_CURRENCY_RE = re.compile(r"(?:rs\.?|inr|₹)", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"-?\d+(?:\.\d+)?")

MAX_REASONABLE_AMOUNT = Decimal("100000000")


def parse_decimal_amount(raw: str | None, *, signed: bool = False) -> Decimal | None:
    if raw is None:
        return None
    text = _CURRENCY_RE.sub("", raw).replace(",", "").strip()
    is_negative = False
    if signed and text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1]
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    try:
        value = Decimal(match.group(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    if not signed:
        value = value.copy_abs()
    elif is_negative:
        value = -value
    return value


def resolve_credit_flag(raw_type: str) -> bool | None:
    value = " ".join((raw_type or "").upper().replace(".", " ").split())
    if value in {"CR", "C", "CREDIT", "DEPOSIT"} or value.endswith(" CR"):
        return True
    if value in {"DR", "D", "DEBIT", "WITHDRAWAL"} or value.endswith(" DR"):
        return False
    return None


def validate_transaction(
    raw: RawTransaction,
    *,
    statement_period: StatementPeriod | None = None,
    category_hint: str | None = None,
) -> ValidatedTransaction:
    errors: list[str] = []
    soft_errors: list[str] = []

    txn_date = parse_indian_date(raw.date_raw)
    if txn_date is None:
        errors.append("date_parse_failed")
        txn_date = date.min
    else:
        if txn_date > date.today():
            errors.append("date_not_future")
        if txn_date.year < 1990:
            errors.append("date_not_before_1990")
        if statement_period and not (statement_period.start <= txn_date <= statement_period.end):
            soft_errors.append("date_within_statement_period")

    amount = parse_decimal_amount(raw.amount_raw)
    if amount is None:
        errors.append("amount_parse_failed")
        amount = Decimal("0.00")
    else:
        if amount <= 0:
            errors.append("amount_positive")
        if amount >= MAX_REASONABLE_AMOUNT:
            errors.append("amount_not_absurd")
        if not _amount_has_max_two_decimals(raw.amount_raw):
            errors.append("amount_max_2_decimal")

    balance_after = parse_decimal_amount(raw.balance_raw, signed=True) if raw.balance_raw else None
    if balance_after is not None and balance_after < 0:
        soft_errors.append("balance_negative")

    is_credit = resolve_credit_flag(raw.txn_type_raw)
    if is_credit is None:
        soft_errors.append("cr_dr_resolved")

    description = normalize_description(raw.description_raw)
    if not description:
        errors.append("description_required")

    all_errors = errors + soft_errors
    # Honor the runtime-tunable promotion threshold so operators can dial trust
    # up or down per environment without redeploying. Clamp into a safe range.
    confidence_floor = max(0.0, min(1.0, settings.promotion_confidence_threshold))
    if errors:
        status = ValidationStatus.INVALID
    elif raw.confidence < confidence_floor:
        status = ValidationStatus.LOW_CONFIDENCE
    elif soft_errors:
        status = ValidationStatus.NEEDS_REVIEW
    else:
        status = ValidationStatus.VALID

    return ValidatedTransaction(
        txn_date=txn_date,
        description=description,
        amount=amount,
        is_credit=is_credit,
        balance_after=balance_after,
        category_hint=category_hint,
        raw=raw,
        validation_status=status,
        validation_errors=all_errors,
    )


def normalize_description(value: str) -> str:
    return _SPACE_RE.sub(" ", (value or "").strip())


def _amount_has_max_two_decimals(raw: str) -> bool:
    text = _CURRENCY_RE.sub("", raw).replace(",", "").strip()
    match = _AMOUNT_RE.search(text)
    if not match:
        return False
    _, _, fractional = match.group(0).partition(".")
    return not fractional or len(fractional) <= 2


def dedup_key(account_id: str | int, txn: ValidatedTransaction) -> str:
    description = normalize_description(txn.description).lower()[:40]
    paise = int((txn.amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    direction = "cr" if txn.is_credit else "dr"
    raw = "|".join(
        [
            str(account_id),
            txn.txn_date.isoformat(),
            str(paise),
            description,
            direction,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def balance_walk_check(
    txns: list[ValidatedTransaction],
    opening_balance: Decimal,
    closing_balance: Decimal,
    threshold: Decimal = Decimal("1.00"),
) -> BalanceWalkResult:
    running = opening_balance
    problematic: list[BalanceWalkProblem] = []

    for idx, txn in sorted(enumerate(txns), key=lambda item: item[1].txn_date):
        if txn.validation_status == ValidationStatus.INVALID or txn.is_credit is None:
            problematic.append(_balance_walk_problem(idx, txn))
            continue

        running = running + txn.amount if txn.is_credit else running - txn.amount
        if txn.balance_after is not None:
            discrepancy = abs(running - txn.balance_after)
            if discrepancy > threshold:
                problematic.append(_balance_walk_problem(idx, txn))
                running = txn.balance_after

    delta = abs(running - closing_balance)
    return BalanceWalkResult(
        passed=delta <= threshold,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        computed_closing=running,
        delta=delta,
        delta_threshold=threshold,
        problematic_txns=problematic,
    )


def _balance_walk_problem(index: int, txn: ValidatedTransaction) -> BalanceWalkProblem:
    return BalanceWalkProblem(
        index_in_input=index,
        txn_date=txn.txn_date,
        amount=txn.amount,
        description_prefix=normalize_description(txn.description)[:40],
    )
