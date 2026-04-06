import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TaxPortalData(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tax_portal_data"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    document_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_artifacts.id", ondelete="SET NULL")
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    assessment_year: Mapped[str | None] = mapped_column(String(16))
    financial_year: Mapped[str | None] = mapped_column(String(16))
    source_name: Mapped[str | None] = mapped_column(String(100))
    pan_masked: Mapped[str | None] = mapped_column(String(20))
    document_date: Mapped[date | None] = mapped_column(Date)
    extracted_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verification_json: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsed")
    notes: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", back_populates="tax_portal_records")

