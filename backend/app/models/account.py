import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "institution_name",
            "account_type",
            "account_number_masked",
            name="uq_accounts_user_institution_type_masked",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id")
    )
    institution_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)
    account_number_masked: Mapped[str | None] = mapped_column(String(50))
    nickname: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    last_statement_date: Mapped[date | None] = mapped_column(Date)
    opening_date: Mapped[date | None] = mapped_column(Date)

    user = relationship("User", back_populates="accounts")
    institution = relationship("Institution", back_populates="accounts")
    statements = relationship("Statement", back_populates="account")
    balance_snapshots = relationship("BalanceSnapshot", back_populates="account")
