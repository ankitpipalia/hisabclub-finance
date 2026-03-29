import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class InstitutionPasswordPattern(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "institution_password_patterns"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "bank_code",
            "account_scope",
            name="uq_institution_password_pattern_scope",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    bank_code: Mapped[str] = mapped_column(String(30), nullable=False)
    account_scope: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # credit_card | bank_account | any
    pattern_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # template | static_password
    pattern_template: Mapped[str] = mapped_column(String(255), nullable=False)
    variables_json: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
