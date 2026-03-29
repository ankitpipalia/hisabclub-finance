import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class TransferMatch(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transfer_matches"
    __table_args__ = (
        UniqueConstraint("debit_canonical_id", "credit_canonical_id", name="uq_transfer_matches_debit_credit"),
        CheckConstraint("debit_canonical_id <> credit_canonical_id", name="ck_transfer_matches_distinct_legs"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_transfer_matches_confidence"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    debit_canonical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_transactions.id", ondelete="CASCADE"), nullable=False
    )
    credit_canonical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_transactions.id", ondelete="CASCADE"), nullable=False
    )
    match_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    debit_transaction = relationship(
        "CanonicalTransaction",
        foreign_keys=[debit_canonical_id],
        back_populates="transfer_matches_as_debit",
    )
    credit_transaction = relationship(
        "CanonicalTransaction",
        foreign_keys=[credit_canonical_id],
        back_populates="transfer_matches_as_credit",
    )
