import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RawSms(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "raw_sms"
    __table_args__ = (
        UniqueConstraint("user_id", "sms_hash", name="uq_raw_sms_user_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    sms_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_address: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sms_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    classification: Mapped[str | None] = mapped_column(String(50))
    bank_name: Mapped[str | None] = mapped_column(String(50))
    account_masked: Mapped[str | None] = mapped_column(String(50))
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    direction: Mapped[str | None] = mapped_column(String(10))  # 'debit' | 'credit'
    confidence: Mapped[float | None] = mapped_column(Float)
    device_id: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
