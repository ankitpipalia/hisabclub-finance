"""Local customer-scoped document knowledge for statement parsing."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.llm.sanitizer import sanitize_for_llm
from app.engines.parser.hints import (
    infer_account_type_hint_from_text,
    infer_bank_hint_from_text,
    normalize_parser_hints,
    statement_keyword_tokens,
)
from app.engines.parser.pdf_utils import decrypt_pdf, extract_text
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.statement import Statement


@dataclass
class KnowledgeReference:
    source_filename: str
    bank_hint: str | None
    account_type_hint: str | None
    snippet: str
    score: int
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class StatementKnowledgeContext:
    recent_statement_summaries: list[str] = field(default_factory=list)
    references: list[KnowledgeReference] = field(default_factory=list)
    bank_candidates: list[str] = field(default_factory=list)
    account_type_candidates: list[str] = field(default_factory=list)

    def as_prompt_context(self) -> str:
        sections: list[str] = []
        if self.bank_candidates:
            sections.append(
                "Prior customer bank patterns: " + ", ".join(self.bank_candidates[:6])
            )
        if self.account_type_candidates:
            sections.append(
                "Prior customer account patterns: "
                + ", ".join(self.account_type_candidates[:4])
            )
        if self.recent_statement_summaries:
            sections.append(
                "Recent parsed statements:\n- " + "\n- ".join(self.recent_statement_summaries[:5])
            )
        if self.references:
            rendered = []
            for ref in self.references[:4]:
                page_label = ""
                if ref.page_start is not None:
                    page_label = (
                        f" pages {ref.page_start + 1}-{ref.page_end + 1}"
                        if ref.page_end is not None and ref.page_end != ref.page_start
                        else f" page {ref.page_start + 1}"
                    )
                rendered.append(
                    f"[{ref.source_filename}{page_label}] bank={ref.bank_hint or 'unknown'} "
                    f"type={ref.account_type_hint or 'unknown'} score={ref.score}: {ref.snippet}"
                )
            sections.append("Relevant prior document snippets:\n- " + "\n- ".join(rendered))
        return "\n\n".join(sections).strip()


async def ingest_pdf_knowledge(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    pdf_content: bytes,
    password: str | None,
    source_filename: str,
    source_kind: str,
    raw_pdf_id: uuid.UUID | None = None,
    artifact_id: uuid.UUID | None = None,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    doc_type: str | None = None,
) -> int:
    pdf_bytes = decrypt_pdf(pdf_content, password)
    pages = extract_text(pdf_bytes)
    normalized = normalize_parser_hints(
        bank_hint=bank_hint or infer_bank_hint_from_text("\n".join(pages)),
        account_type_hint=account_type_hint or infer_account_type_hint_from_text("\n".join(pages)),
    )
    chunks = _chunk_pages(pages)

    if raw_pdf_id is not None:
        await db.execute(
            delete(DocumentKnowledgeChunk).where(DocumentKnowledgeChunk.raw_pdf_id == raw_pdf_id)
        )
    if artifact_id is not None:
        await db.execute(
            delete(DocumentKnowledgeChunk).where(DocumentKnowledgeChunk.artifact_id == artifact_id)
        )

    for idx, chunk in enumerate(chunks):
        db.add(
            DocumentKnowledgeChunk(
                user_id=user_id,
                raw_pdf_id=raw_pdf_id,
                artifact_id=artifact_id,
                source_kind=source_kind,
                source_filename=source_filename,
                doc_type=doc_type,
                bank_hint=normalized.bank_hint,
                account_type_hint=normalized.account_type_hint,
                chunk_index=idx,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_hash_sha256=hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                chunk_text=chunk.text,
                metadata_json={"char_count": len(chunk.text)},
            )
        )
    await db.flush()
    return len(chunks)


async def build_statement_knowledge_context(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    current_text: str,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    exclude_raw_pdf_id: uuid.UUID | None = None,
    exclude_artifact_id: uuid.UUID | None = None,
) -> StatementKnowledgeContext:
    normalized = normalize_parser_hints(bank_hint=bank_hint, account_type_hint=account_type_hint)
    query = (
        select(DocumentKnowledgeChunk)
        .where(DocumentKnowledgeChunk.user_id == user_id)
        .order_by(desc(DocumentKnowledgeChunk.created_at))
        .limit(300)
    )
    chunks = (await db.execute(query)).scalars().all()
    if exclude_raw_pdf_id is not None:
        chunks = [chunk for chunk in chunks if chunk.raw_pdf_id != exclude_raw_pdf_id]
    if exclude_artifact_id is not None:
        chunks = [chunk for chunk in chunks if chunk.artifact_id != exclude_artifact_id]

    tokens = statement_keyword_tokens(current_text)
    references = _rank_references(
        chunks=chunks,
        tokens=tokens,
        bank_hint=normalized.bank_hint,
        account_type_hint=normalized.account_type_hint,
    )

    stmt_query = (
        select(Statement)
        .where(Statement.user_id == user_id)
        .order_by(desc(Statement.parsed_at), desc(Statement.created_at))
        .limit(12)
    )
    statements = (await db.execute(stmt_query)).scalars().all()
    recent_statement_summaries = [
        _format_statement_summary(statement)
        for statement in statements
        if (not normalized.bank_hint or statement.bank_name.upper() == normalized.bank_hint)
        and (
            not normalized.account_type_hint
            or normalized.account_type_hint == "auto"
            or (
                normalized.account_type_hint == "credit_card"
                and statement.account_type == "credit_card"
            )
            or (
                normalized.account_type_hint == "bank_account"
                and statement.account_type != "credit_card"
            )
        )
    ]
    if not recent_statement_summaries:
        recent_statement_summaries = [_format_statement_summary(statement) for statement in statements[:5]]

    bank_candidates = _top_counts(
        [chunk.bank_hint for chunk in chunks if chunk.bank_hint],
        max_items=6,
    )
    account_candidates = _top_counts(
        [chunk.account_type_hint for chunk in chunks if chunk.account_type_hint],
        max_items=4,
    )

    return StatementKnowledgeContext(
        recent_statement_summaries=recent_statement_summaries[:5],
        references=references[:4],
        bank_candidates=bank_candidates,
        account_type_candidates=account_candidates,
    )


@dataclass
class _Chunk:
    text: str
    page_start: int | None
    page_end: int | None


def _chunk_pages(pages: list[str], *, max_chars: int = 1800, overlap: int = 240) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    for page_index, page in enumerate(pages):
        normalized = " ".join(page.split())
        if not normalized:
            continue
        if len(normalized) <= max_chars:
            chunks.append(_Chunk(text=normalized, page_start=page_index, page_end=page_index))
            continue
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + max_chars)
            window = normalized[start:end]
            if end < len(normalized):
                split_at = window.rfind(" ")
                if split_at > max_chars // 2:
                    end = start + split_at
                    window = normalized[start:end]
            chunks.append(_Chunk(text=window.strip(), page_start=page_index, page_end=page_index))
            if end >= len(normalized):
                break
            start = max(0, end - overlap)
    return chunks


def _rank_references(
    *,
    chunks: list[DocumentKnowledgeChunk],
    tokens: set[str],
    bank_hint: str | None,
    account_type_hint: str | None,
) -> list[KnowledgeReference]:
    ranked: list[KnowledgeReference] = []
    seen_hashes: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_hash_sha256 in seen_hashes:
            continue
        chunk_tokens = statement_keyword_tokens(chunk.chunk_text, limit=120)
        overlap = len(tokens & chunk_tokens)
        score = overlap
        if bank_hint and chunk.bank_hint == bank_hint:
            score += 8
        if account_type_hint and chunk.account_type_hint == account_type_hint:
            score += 5
        if chunk.doc_type in {"bank_statement", "credit_card_statement"}:
            score += 2
        if score <= 0:
            continue
        seen_hashes.add(chunk.chunk_hash_sha256)
        ranked.append(
            KnowledgeReference(
                source_filename=chunk.source_filename,
                bank_hint=chunk.bank_hint,
                account_type_hint=chunk.account_type_hint,
                snippet=sanitize_for_llm(chunk.chunk_text[:500]),
                score=score,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def _format_statement_summary(statement: Statement) -> str:
    period = None
    if statement.statement_period_start and statement.statement_period_end:
        period = f"{statement.statement_period_start}..{statement.statement_period_end}"
    elif statement.statement_period_end:
        period = str(statement.statement_period_end)
    else:
        period = "unknown-period"
    return (
        f"{statement.bank_name} {statement.account_type} "
        f"acct={statement.account_number_masked or 'unknown'} "
        f"period={period} txns={statement.transaction_count or 0} "
        f"parser={statement.parser_used}"
    )


def _top_counts(values: list[str | None], *, max_items: int) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [f"{value} ({count})" for value, count in ranked[:max_items]]
