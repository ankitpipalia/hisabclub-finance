import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TransactionAnnotation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transaction_annotations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    parsed_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parsed_transactions.id", ondelete="CASCADE")
    )
    canonical_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_transactions.id", ondelete="CASCADE")
    )
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id", ondelete="CASCADE"), nullable=False
    )
    annotation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    llm_response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    actions_json: Mapped[dict | None] = mapped_column(JSONB)
    page_number: Mapped[int | None] = mapped_column(Integer)

    user = relationship("User", back_populates="transaction_annotations")
    statement = relationship("Statement", back_populates="annotations")
    parsed_transaction = relationship("ParsedTransaction", back_populates="annotations")
    canonical_transaction = relationship("CanonicalTransaction")

