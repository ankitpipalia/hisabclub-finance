import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanonicalTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Core transaction data
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # 'debit' | 'credit'
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    transaction_nature: Mapped[str] = mapped_column(
        String(30), default="expense", nullable=False
    )
    # 'expense' | 'income' | 'transfer_internal' | 'refund' | 'investment' | 'tax' | ...

    # Merchant info
    merchant_raw: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_normalized: Mapped[str | None] = mapped_column(Text)
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id")
    )

    # Category
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id")
    )
    category_source: Mapped[str] = mapped_column(
        String(10), default="auto", nullable=False
    )  # 'auto' | 'user' | 'llm'

    # Account info
    account_masked: Mapped[str | None] = mapped_column(String(50))
    bank_name: Mapped[str | None] = mapped_column(String(50))
    account_type: Mapped[str | None] = mapped_column(String(50))

    # Foreign exchange
    foreign_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    foreign_currency: Mapped[str | None] = mapped_column(String(3))

    # Flags
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anomaly_reason: Mapped[str | None] = mapped_column(Text)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # User additions
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    user = relationship("User", back_populates="canonical_transactions")
    merchant = relationship("Merchant")
    category = relationship("Category")
    sources = relationship("TransactionSource", back_populates="canonical_transaction")
