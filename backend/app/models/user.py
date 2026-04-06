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
    last_name: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[str | None] = mapped_column(String(10))  # DDMMYYYY format
    pan_number_encrypted: Mapped[str | None] = mapped_column(Text)
    onboarding_completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    onboarding_step: Mapped[int] = mapped_column(default=0, nullable=False)

    statements = relationship("Statement", back_populates="user")
    canonical_transactions = relationship("CanonicalTransaction", back_populates="user")
    accounts = relationship("Account", back_populates="user")
    balance_snapshots = relationship("BalanceSnapshot", back_populates="user")
    transaction_annotations = relationship("TransactionAnnotation", back_populates="user")
    conversation_threads = relationship("ConversationThread", back_populates="user")
    conversation_messages = relationship("ConversationMessage", back_populates="user")
    tax_portal_records = relationship("TaxPortalData", back_populates="user")
