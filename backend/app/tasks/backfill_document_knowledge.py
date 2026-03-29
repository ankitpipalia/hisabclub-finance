"""Backfill local document knowledge chunks from existing PDFs."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import exists, select

from app.config import settings
from app.database import async_session_factory
from app.engines.llm.knowledge import ingest_pdf_knowledge
from app.models.document_artifact import DocumentArtifact
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.security.tenant_context import apply_rls_db_role, set_worker_context


async def main() -> None:
    raw_ingested = 0
    artifact_ingested = 0
    skipped = 0
    async with async_session_factory() as db:
        if settings.db_set_role_on_connect:
            await apply_rls_db_role(db, role_name=settings.db_rls_role)
        await set_worker_context(db)
        raw_rows = (
            await db.execute(
                select(RawPdf).where(
                    ~exists(
                        select(DocumentKnowledgeChunk.id).where(
                            DocumentKnowledgeChunk.raw_pdf_id == RawPdf.id
                        )
                    )
                )
            )
        ).scalars().all()
        for raw_pdf in raw_rows:
            path = Path(raw_pdf.storage_path)
            if not path.exists():
                skipped += 1
                continue
            try:
                content = path.read_bytes()
                statement = (
                    await db.execute(
                        select(Statement).where(Statement.pdf_id == raw_pdf.id).limit(1)
                    )
                ).scalar_one_or_none()
                await ingest_pdf_knowledge(
                    db=db,
                    user_id=raw_pdf.user_id,
                    pdf_content=content,
                    password=None,
                    source_filename=raw_pdf.original_filename,
                    source_kind="raw_pdf",
                    raw_pdf_id=raw_pdf.id,
                    bank_hint=statement.bank_name if statement else None,
                    account_type_hint=(
                        "credit_card"
                        if statement and statement.account_type == "credit_card"
                        else "bank_account"
                        if statement and statement.account_type in {"savings", "current"}
                        else None
                    ),
                    doc_type=(
                        "credit_card_statement"
                        if statement and statement.account_type == "credit_card"
                        else "bank_statement"
                    ),
                )
                raw_ingested += 1
            except Exception:
                skipped += 1

        artifact_rows = (
            await db.execute(
                select(DocumentArtifact).where(
                    DocumentArtifact.file_ext == "pdf",
                    ~exists(
                        select(DocumentKnowledgeChunk.id).where(
                            DocumentKnowledgeChunk.artifact_id == DocumentArtifact.id
                        )
                    ),
                )
            )
        ).scalars().all()
        for artifact in artifact_rows:
            path = Path(artifact.file_path)
            if not path.exists():
                skipped += 1
                continue
            try:
                content = path.read_bytes()
                await ingest_pdf_knowledge(
                    db=db,
                    user_id=artifact.user_id,
                    pdf_content=content,
                    password=None,
                    source_filename=artifact.file_name,
                    source_kind="artifact",
                    artifact_id=artifact.id,
                    bank_hint=artifact.bank_hint,
                    doc_type=artifact.doc_type,
                )
                artifact_ingested += 1
            except Exception:
                skipped += 1

        await db.commit()

    print(
        {
            "raw_ingested": raw_ingested,
            "artifact_ingested": artifact_ingested,
            "skipped": skipped,
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
