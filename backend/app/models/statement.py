import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


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
    parse_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | parsing | success | partial | failed
    parse_errors: Mapped[dict | None] = mapped_column(JSONB)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transaction_count: Mapped[int | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="statements")
    pdf = relationship("RawPdf", back_populates="statement")
    parsed_transactions = relationship("ParsedTransaction", back_populates="statement")
