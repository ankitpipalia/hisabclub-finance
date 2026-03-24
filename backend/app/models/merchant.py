import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class Merchant(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "merchants"

    name_normalized: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id")
    )
    merchant_type: Mapped[str | None] = mapped_column(String(50))  # 'online' | 'pos' | 'utility'
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    default_category = relationship("Category")
    patterns = relationship("MerchantPattern", back_populates="merchant", cascade="all,delete-orphan")


class MerchantPattern(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "merchant_patterns"

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_type: Mapped[str] = mapped_column(
        String(20), default="contains", nullable=False
    )  # 'contains' | 'regex' | 'exact'
    bank_hint: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    merchant = relationship("Merchant", back_populates="patterns")
