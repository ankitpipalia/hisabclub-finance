import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConversationThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_threads"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    summary: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    user = relationship("User", back_populates="conversation_threads")
    statement = relationship("Statement", back_populates="conversation_threads")
    messages = relationship(
        "ConversationMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at.asc()",
    )


class ConversationMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_threads.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    thread = relationship("ConversationThread", back_populates="messages")
    user = relationship("User", back_populates="conversation_messages")

