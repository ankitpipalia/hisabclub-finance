import uuid

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Institution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (
        UniqueConstraint("name", name="uq_institutions_name"),
        UniqueConstraint("short_name", name="uq_institutions_short_name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    short_name: Mapped[str] = mapped_column(String(20), nullable=False)
    logo_key: Mapped[str | None] = mapped_column(String(50))
    institution_type: Mapped[str] = mapped_column(String(30), nullable=False, default="bank")
    supported_formats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    accounts = relationship("Account", back_populates="institution")

