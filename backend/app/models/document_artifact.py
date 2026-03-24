import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class DocumentArtifact(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_artifacts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_ext: Mapped[str] = mapped_column(String(20), nullable=False)
    file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    doc_subtype: Mapped[str | None] = mapped_column(String(50))
    bank_hint: Mapped[str | None] = mapped_column(String(50))

    status: Mapped[str] = mapped_column(
        String(20), default="discovered", nullable=False
    )  # discovered | parsed | skipped | failed
    parse_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

