import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class ParsedTransaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "parsed_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'statement' | 'sms' | 'manual'
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )  # statements.id or raw_sms.id
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id")
    )

    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date)
    description_raw: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 'debit' | 'credit'
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    foreign_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    foreign_currency: Mapped[str | None] = mapped_column(String(3))

    reference_number: Mapped[str | None] = mapped_column(String(100))
    upi_id: Mapped[str | None] = mapped_column(String(255))
    dedupe_fingerprint: Mapped[str | None] = mapped_column(String(64))

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    override_reason_code: Mapped[str | None] = mapped_column(String(60))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_method: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'template' | 'ocr' | 'llm' | 'sms_regex'
    line_number: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    statement = relationship("Statement", back_populates="parsed_transactions")
    transaction_sources = relationship("TransactionSource", back_populates="parsed_transaction")
    annotations = relationship("TransactionAnnotation", back_populates="parsed_transaction")
