import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class TransactionSplit(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transaction_splits"
    __table_args__ = (
        UniqueConstraint(
            "source_canonical_txn_id",
            "split_index",
            name="uq_transaction_splits_source_index",
        ),
        UniqueConstraint(
            "child_canonical_txn_id",
            name="uq_transaction_splits_child",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    source_canonical_txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_transactions.id", ondelete="CASCADE"), nullable=False
    )
    child_canonical_txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_transactions.id", ondelete="CASCADE"), nullable=False
    )
    split_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
