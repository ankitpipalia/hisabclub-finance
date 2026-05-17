from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class ExtractionSource(str, Enum):
    TEMPLATE = "template"
    LLM_TEXT = "llm_text"
    LLM_VISION = "llm_vision"
    OCR_LLM = "ocr_llm"
    MANUAL = "manual"
    SMS = "sms"


class ValidationStatus(str, Enum):
    VALID = "valid"
    LOW_CONFIDENCE = "low_confidence"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class StatementPeriod:
    start: date
    end: date


@dataclass
class RawTransaction:
    """Output of extraction stage before field validation."""

    date_raw: str
    description_raw: str
    amount_raw: str
    balance_raw: str | None
    txn_type_raw: str
    page_number: int
    char_offset: int
    confidence: float
    source: ExtractionSource
    source_evidence: dict[str, Any]


@dataclass
class ValidatedTransaction:
    """Normalized transaction with source lineage preserved."""

    txn_date: date
    description: str
    amount: Decimal
    is_credit: bool | None
    balance_after: Decimal | None
    category_hint: str | None
    raw: RawTransaction
    validation_status: ValidationStatus
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class BalanceWalkProblem:
    index_in_input: int
    txn_date: date
    amount: Decimal
    description_prefix: str

    def identity_key(self) -> tuple[date, Decimal, str]:
        return (self.txn_date, self.amount, self.description_prefix)

    def to_dict(self) -> dict[str, str | int]:
        return {
            "index_in_input": self.index_in_input,
            "txn_date": self.txn_date.isoformat(),
            "amount": str(self.amount),
            "description_prefix": self.description_prefix,
        }


@dataclass
class BalanceWalkResult:
    passed: bool
    opening_balance: Decimal
    closing_balance: Decimal
    computed_closing: Decimal
    delta: Decimal
    delta_threshold: Decimal = Decimal("1.00")
    problematic_txns: list[BalanceWalkProblem] = field(default_factory=list)
