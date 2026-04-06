import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BalanceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("statement_id", name="uq_balance_snapshots_statement_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id")
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id", ondelete="CASCADE")
    )
    position_key: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )  # manual | statement
    entry_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="asset"
    )  # asset | liability
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(100))
    account_masked: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    user = relationship("User", back_populates="balance_snapshots")
    account = relationship("Account", back_populates="balance_snapshots")
    statement = relationship("Statement", back_populates="balance_snapshots")
