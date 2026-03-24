from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # Profile fields for password auto-generation
    first_name: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[str | None] = mapped_column(String(10))  # DDMMYYYY format

    statements = relationship("Statement", back_populates="user")
    canonical_transactions = relationship("CanonicalTransaction", back_populates="user")
