import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class Bill(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    bank_name: Mapped[str] = mapped_column(String(50), nullable=False)
    account_masked: Mapped[str | None] = mapped_column(String(50))
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=True
    )

    billing_period_start: Mapped[date | None] = mapped_column(Date)
    billing_period_end: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_due: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    min_due: Mapped[float | None] = mapped_column(Numeric(12, 2))

    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    paid_date: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    statement = relationship("Statement")
