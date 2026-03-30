import logging
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, UUIDPrimaryKeyMixin

logger = logging.getLogger(__name__)

STATEMENT_PARSE_STATUS_ALLOWED = {
    "uploaded",
    "classifying",
    "extracting",
    "validating",
    "review_required",
    "parsed",
    "partial",
    "failed",
}

STATEMENT_PARSE_STATUS_LEGACY_MAP = {
    "success": "parsed",
    "no_transactions": "partial",
    "pending": "uploaded",
    "parsing": "extracting",
}


def normalize_statement_parse_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return "uploaded"
    normalized = STATEMENT_PARSE_STATUS_LEGACY_MAP.get(normalized, normalized)
    if normalized in STATEMENT_PARSE_STATUS_ALLOWED:
        return normalized
    logger.warning("Unknown statement parse_status '%s' normalized to 'failed'", value)
    return "failed"


class Statement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "statements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    pdf_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_pdfs.id")
    )
    bank_name: Mapped[str] = mapped_column(String(50), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'credit_card' | 'savings' | 'current'
    account_number_masked: Mapped[str | None] = mapped_column(String(50))

    statement_period_start: Mapped[date | None] = mapped_column(Date)
    statement_period_end: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    min_amount_due: Mapped[float | None] = mapped_column(Numeric(12, 2))
    total_amount_due: Mapped[float | None] = mapped_column(Numeric(12, 2))
    credit_limit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    available_limit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    opening_balance: Mapped[float | None] = mapped_column(Numeric(12, 2))
    closing_balance: Mapped[float | None] = mapped_column(Numeric(12, 2))
    previous_balance: Mapped[float | None] = mapped_column(Numeric(12, 2))
    payments_received: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    parser_used: Mapped[str] = mapped_column(String(100), nullable=False)
    # uploaded | classifying | extracting | validating | review_required | parsed | partial | failed
    parse_status: Mapped[str] = mapped_column(
        String(20), default="uploaded", nullable=False
    )
    parse_errors: Mapped[dict | None] = mapped_column(JSONB)
    expected_row_count: Mapped[int | None] = mapped_column()
    extracted_row_count: Mapped[int | None] = mapped_column()
    promoted_row_count: Mapped[int | None] = mapped_column()
    quarantined_row_count: Mapped[int | None] = mapped_column()
    yield_rate: Mapped[float | None] = mapped_column(Float)
    statement_fingerprint: Mapped[str | None] = mapped_column(String(64))
    version_no: Mapped[int] = mapped_column(default=1, nullable=False)
    supersedes_statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id")
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transaction_count: Mapped[int | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="statements")
    pdf = relationship("RawPdf", back_populates="statement")
    parsed_transactions = relationship("ParsedTransaction", back_populates="statement")

    @validates("parse_status")
    def _validate_parse_status(self, _key: str, value: str | None) -> str:
        return normalize_statement_parse_status(value)
