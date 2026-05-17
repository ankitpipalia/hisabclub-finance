import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    dedupe_fingerprint: Mapped[str | None] = mapped_column(String(64))

    # Extraction audit and typed-pipeline lineage.
    extraction_source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    source_statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id", ondelete="SET NULL")
    )
    source_page_number: Mapped[int | None] = mapped_column(Integer)
    source_char_offset: Mapped[int | None] = mapped_column(Integer)
    source_evidence: Mapped[dict | None] = mapped_column(JSONB)
    dedup_key: Mapped[str | None] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(20), default="valid", nullable=False)
    validation_errors: Mapped[list[str] | None] = mapped_column(JSONB)
    balance_walk_passed: Mapped[bool | None] = mapped_column(Boolean)
    review_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_tasks.id", ondelete="SET NULL")
    )
    user_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    override_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    source_statement = relationship("Statement", foreign_keys=[source_statement_id])
    review_task = relationship("ReviewTask", foreign_keys=[review_task_id])
    sources = relationship("TransactionSource", back_populates="canonical_transaction")
    transfer_matches_as_debit = relationship(
        "TransferMatch",
        foreign_keys="TransferMatch.debit_canonical_id",
        back_populates="debit_transaction",
    )
    transfer_matches_as_credit = relationship(
        "TransferMatch",
        foreign_keys="TransferMatch.credit_canonical_id",
        back_populates="credit_transaction",
    )
