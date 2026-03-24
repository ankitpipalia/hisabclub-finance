"""ConnectedAccount model — stores OAuth credentials for external integrations (e.g. Gmail)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConnectedAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connected_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'gmail'
    provider_email: Mapped[str | None] = mapped_column(String(255))
    credentials_enc: Mapped[str | None] = mapped_column(
        Text
    )  # Encrypted JSON with OAuth tokens

    sender_allowlist: Mapped[list | None] = mapped_column(
        JSONB, default=list
    )  # List of allowed sender emails

    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )  # 'active' | 'revoked' | 'error'
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User")
