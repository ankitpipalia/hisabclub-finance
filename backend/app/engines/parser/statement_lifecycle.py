"""Statement lifecycle helpers: delete and re-review with local knowledge cleanup."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.ledger.transfer_reclassifier import reclassify_transfer_payments_for_user
from app.engines.llm.knowledge import ingest_pdf_knowledge
from app.engines.parser.base import parse_statement
from app.engines.parser.password_patterns import resolve_pdf_password
from app.engines.parser.pdf_utils import decrypt_pdf
from app.models.canonical_transaction import CanonicalTransaction
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.parsed_transaction import ParsedTransaction
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement
from app.models.transaction_source import TransactionSource


@dataclass
class StatementDeleteResult:
    deleted_statement_id: uuid.UUID
    deleted_parsed_transactions: int
    deleted_canonical_transactions: int
    deleted_pdf_id: uuid.UUID | None


async def delete_statement_and_memory(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    statement: Statement,
    remove_pdf: bool = True,
) -> StatementDeleteResult:
    parsed_txn_ids = (
        await db.execute(
            select(ParsedTransaction.id).where(
                ParsedTransaction.user_id == user_id,
                ParsedTransaction.statement_id == statement.id,
            )
        )
    ).scalars().all()

    deleted_canonical = 0
    if parsed_txn_ids:
        canonical_ids = (
            await db.execute(
                select(TransactionSource.canonical_txn_id)
                .where(TransactionSource.parsed_txn_id.in_(parsed_txn_ids))
                .distinct()
            )
        ).scalars().all()

        await db.execute(
            delete(TransactionSource).where(TransactionSource.parsed_txn_id.in_(parsed_txn_ids))
        )
        await db.execute(delete(ParsedTransaction).where(ParsedTransaction.id.in_(parsed_txn_ids)))

        for canonical_id in canonical_ids:
            remaining = (
                await db.execute(
                    select(TransactionSource.id)
                    .where(TransactionSource.canonical_txn_id == canonical_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if remaining is None:
                await db.execute(
                    delete(CanonicalTransaction).where(CanonicalTransaction.id == canonical_id)
                )
                deleted_canonical += 1

    await db.execute(delete(Statement).where(Statement.id == statement.id))

    deleted_pdf_id: uuid.UUID | None = statement.pdf_id
    if remove_pdf and statement.pdf_id:
        raw_pdf = (
            await db.execute(
                select(RawPdf)
                .where(RawPdf.id == statement.pdf_id, RawPdf.user_id == user_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if raw_pdf is not None:
            await db.execute(
                delete(DocumentKnowledgeChunk).where(
                    DocumentKnowledgeChunk.raw_pdf_id == raw_pdf.id
                )
            )
            await db.execute(delete(RawPdf).where(RawPdf.id == raw_pdf.id))
            _remove_file_if_exists(raw_pdf.storage_path)
            debug_text_path = _debug_text_path(raw_pdf.storage_path)
            if debug_text_path:
                _remove_file_if_exists(debug_text_path)
    return StatementDeleteResult(
        deleted_statement_id=statement.id,
        deleted_parsed_transactions=len(parsed_txn_ids),
        deleted_canonical_transactions=deleted_canonical,
        deleted_pdf_id=deleted_pdf_id,
    )


async def rereview_statement_with_llm(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    statement: Statement,
) -> Statement:
    if not settings.llm_enabled:
        raise ValueError("Local LLM is disabled. Enable LLM_ENABLED=true before re-review.")
    if not statement.pdf_id:
        raise ValueError("This statement has no source PDF attached.")

    raw_pdf = (
        await db.execute(
            select(RawPdf).where(RawPdf.id == statement.pdf_id, RawPdf.user_id == user_id).limit(1)
        )
    ).scalar_one_or_none()
    if raw_pdf is None:
        raise ValueError("Source PDF could not be found for this statement.")

    resolved_path = _resolve_storage_path(raw_pdf.storage_path)
    if not resolved_path or not os.path.exists(resolved_path):
        raise ValueError("Source PDF is missing on disk.")

    pdf_content = open(resolved_path, "rb").read()
    pdf_password = await _resolve_pdf_password_if_possible(
        db=db,
        user_id=user_id,
        pdf_content=pdf_content,
        bank_hint=statement.bank_name,
        account_type_hint=(
            "credit_card" if statement.account_type == "credit_card" else "bank_account"
        ),
        source_filename=raw_pdf.original_filename,
    )

    await delete_statement_and_memory(
        db=db,
        user_id=user_id,
        statement=statement,
        remove_pdf=False,
    )

    await ingest_pdf_knowledge(
        db=db,
        user_id=user_id,
        pdf_content=pdf_content,
        password=pdf_password,
        source_filename=raw_pdf.original_filename,
        source_kind="raw_pdf",
        raw_pdf_id=raw_pdf.id,
        bank_hint=statement.bank_name,
        account_type_hint=(
            "credit_card" if statement.account_type == "credit_card" else "bank_account"
        ),
        doc_type=(
            "credit_card_statement" if statement.account_type == "credit_card" else "bank_statement"
        ),
    )

    reparsed = await parse_statement(
        db=db,
        user_id=user_id,
        pdf_id=raw_pdf.id,
        pdf_content=pdf_content,
        password=pdf_password,
        bank_hint=statement.bank_name,
        account_type_hint=(
            "credit_card" if statement.account_type == "credit_card" else "bank_account"
        ),
        prefer_llm=True,
        allow_semantic_duplicate=True,
    )

    if (reparsed.transaction_count or 0) > 0:
        await reclassify_transfer_payments_for_user(
            db=db,
            user_id=user_id,
            days=3650,
            limit=10000,
            max_gap_days=7,
            use_llm=True,
        )
    return reparsed


def _remove_file_if_exists(path: str | None) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def _debug_text_path(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    root, ext = os.path.splitext(storage_path)
    if ext.lower() == ".pdf":
        return f"{root}_text.txt"
    return None


def _resolve_storage_path(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    if os.path.exists(storage_path):
        return storage_path
    if storage_path.startswith("/app/uploads/"):
        relative = storage_path.removeprefix("/app/uploads/").lstrip("/")
        candidate = os.path.join(settings.upload_dir, relative)
        if os.path.exists(candidate):
            return candidate
    return storage_path


async def _resolve_pdf_password_if_possible(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    pdf_content: bytes,
    bank_hint: str | None,
    account_type_hint: str | None,
    source_filename: str | None,
) -> str | None:
    try:
        decrypt_pdf(pdf_content, None)
        return None
    except ValueError:
        pass

    resolution = await resolve_pdf_password(
        db=db,
        user_id=user_id,
        pdf_content=pdf_content,
        bank_hint=bank_hint,
        account_type_hint=account_type_hint,
        source_filename=source_filename,
    )
    if resolution.password:
        return resolution.password
    raise ValueError(
        "This PDF is password-protected and no saved password pattern matched. "
        "Add a password pattern first, then retry re-review."
    )
