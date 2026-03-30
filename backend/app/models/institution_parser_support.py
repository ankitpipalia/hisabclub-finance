from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class InstitutionParserSupport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "institution_parser_support"
    __table_args__ = (
        UniqueConstraint("bank_code", "account_type", name="uq_institution_parser_support"),
    )

    bank_code: Mapped[str] = mapped_column(String(30), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parser_id: Mapped[str | None] = mapped_column(String(120))
    parser_version: Mapped[str | None] = mapped_column(String(60))
    is_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_layout_signatures: Mapped[dict | None] = mapped_column(JSONB)
    observed_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_expected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_extracted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
