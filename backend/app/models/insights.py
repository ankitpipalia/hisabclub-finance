import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class MonthlySummary(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "monthly_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "year_month", name="uq_monthly_summary_user_month"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    year_month: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # e.g. '2026-03'

    total_income: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    total_expense: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    net_flow: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )

    category_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    top_merchants: Mapped[list | None] = mapped_column(JSONB)
    transaction_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")


class RecurringPattern(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recurring_patterns"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id")
    )
    description_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    typical_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    amount_variance: Mapped[float] = mapped_column(
        Numeric(8, 4), default=0, nullable=False
    )
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'monthly' | 'quarterly' | 'yearly'
    expected_day: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_expected: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    merchant = relationship("Merchant")
    category = relationship("Category")
