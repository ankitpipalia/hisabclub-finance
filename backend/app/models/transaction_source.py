import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class TransactionSource(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transaction_sources"

    canonical_txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parsed_txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parsed_transactions.id"), nullable=False
    )
    match_confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    match_method: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # 'exact_ref' | 'amount_date_desc' | 'fuzzy' | 'manual' | 'single_source'
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    canonical_transaction = relationship(
        "CanonicalTransaction", back_populates="sources"
    )
    parsed_transaction = relationship(
        "ParsedTransaction", back_populates="transaction_sources"
    )
