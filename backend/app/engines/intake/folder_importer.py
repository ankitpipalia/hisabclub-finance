"""Bulk local-folder intake with document registry and statement parsing."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.intake.doc_classifier import classify_document
from app.engines.intake.tax_document_parser import extract_tax_document_metadata
from app.engines.ledger.transfer_reclassifier import reclassify_transfer_payments_for_user
from app.engines.llm.knowledge import ingest_pdf_knowledge
from app.engines.parser.base import StatementDuplicateError, parse_statement
from app.engines.parser.pdf_utils import decrypt_pdf
from app.engines.parser.pdf_utils import extract_text as extract_pdf_text
from app.models.document_artifact import DocumentArtifact
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.raw_pdf import RawPdf


@dataclass
class FolderImportResult:
    discovered: int = 0
    ingested: int = 0
    parsed: int = 0
    skipped: int = 0
    failed: int = 0
    by_doc_type: dict[str, int] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    def add_doc_type(self, doc_type: str) -> None:
        self.by_doc_type[doc_type] = self.by_doc_type.get(doc_type, 0) + 1


async def import_folder(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_path: str,
    parse_supported: bool = True,
    dry_run: bool = False,
    force_reprocess: bool = False,
    password_map: dict[str, str] | None = None,
    max_files: int | None = None,
) -> FolderImportResult:
    root = _resolve_folder_path(folder_path)
    if not root.exists():
        raise ValueError(
            "Folder path does not exist on backend host. "
            f"Resolved path: {root}"
        )
    if not root.is_dir():
        raise ValueError(
            "Provided folder path is not a directory. "
            f"Resolved path: {root}"
        )
    _validate_path_allowed(root)

    result = FolderImportResult()
    files = sorted([p for p in root.rglob("*") if p.is_file()])
    if max_files is not None:
        files = files[:max_files]

    for path in files:
        result.discovered += 1
        classified = classify_document(str(path))
        result.add_doc_type(classified.doc_type)

        file_hash = _sha256_file(path)
        size_bytes = path.stat().st_size

        # Dedup in registry
        existing_artifact = (
            await db.execute(
                select(DocumentArtifact).where(
                    DocumentArtifact.user_id == user_id,
                    DocumentArtifact.file_hash_sha256 == file_hash,
                ).limit(1)
            )
        ).scalar_one_or_none()
        artifact: DocumentArtifact
        if existing_artifact:
            if force_reprocess:
                artifact = existing_artifact
                artifact.file_path = str(path)
                artifact.file_name = path.name
                artifact.file_ext = path.suffix.lower().lstrip(".")
                artifact.file_size_bytes = size_bytes
                artifact.doc_type = classified.doc_type
                artifact.doc_subtype = classified.doc_subtype
                artifact.bank_hint = classified.bank_hint
                artifact.status = "discovered"
                artifact.parse_message = None
            elif (
                not dry_run
                and existing_artifact.status == "skipped"
                and existing_artifact.parse_message == "Dry run only"
            ):
                artifact = existing_artifact
                artifact.status = "discovered"
                artifact.parse_message = None
            else:
                result.skipped += 1
                continue
        else:
            artifact = DocumentArtifact(
                user_id=user_id,
                file_path=str(path),
                file_name=path.name,
                file_ext=path.suffix.lower().lstrip("."),
                file_hash_sha256=file_hash,
                file_size_bytes=size_bytes,
                doc_type=classified.doc_type,
                doc_subtype=classified.doc_subtype,
                bank_hint=classified.bank_hint,
                status="discovered",
                metadata_json={"parent_dir": str(path.parent)},
            )
            db.add(artifact)
            await db.flush()
            result.ingested += 1

            # Persist initial metadata only for new records.

        if dry_run:
            artifact.status = "skipped"
            artifact.parse_message = "Dry run only"
            artifact.processed_at = datetime.now(timezone.utc)
            result.skipped += 1
            continue

        should_parse_pdf = (
            parse_supported
            and path.suffix.lower() == ".pdf"
            and (
                classified.doc_type in {"bank_statement", "credit_card_statement"}
                or (
                    classified.doc_type == "unknown_pdf"
                    and _should_attempt_unknown_pdf_parse(path=path, bank_hint=classified.bank_hint)
                )
            )
        )
        if not should_parse_pdf:
            if path.suffix.lower() == ".pdf":
                non_statement_content = b""
                password = _password_for_path(str(path), password_map)
                try:
                    with open(path, "rb") as f:
                        non_statement_content = f.read()
                    await ingest_pdf_knowledge(
                        db=db,
                        user_id=user_id,
                        pdf_content=non_statement_content,
                        password=password,
                        source_filename=path.name,
                        source_kind="artifact",
                        artifact_id=artifact.id,
                        bank_hint=classified.bank_hint,
                        account_type_hint=(
                            "credit_card"
                            if classified.doc_type == "credit_card_statement"
                            else None
                        ),
                        doc_type=classified.doc_type,
                    )
                except Exception:
                    pass
                metadata = dict(artifact.metadata_json or {})
                if classified.doc_type not in {
                    "bank_statement",
                    "credit_card_statement",
                    "unknown_pdf",
                    "unsupported_bank",
                    "unsupported",
                    "unsupported_file",
                }:
                    extracted_text = ""
                    if non_statement_content:
                        try:
                            decrypted = decrypt_pdf(non_statement_content, password)
                            pages = extract_pdf_text(decrypted)
                            extracted_text = "\n".join(pages)
                        except Exception:
                            extracted_text = ""
                    parsed = extract_tax_document_metadata(
                        doc_type=classified.doc_type,
                        text=extracted_text,
                        source_filename=path.name,
                    )
                    metadata.update(parsed)
                metadata["parent_dir"] = str(path.parent)
                artifact.metadata_json = metadata
            artifact.status = "skipped"
            artifact.parse_message = "Registered for non-statement workflow"
            artifact.processed_at = datetime.now(timezone.utc)
            result.skipped += 1
            continue

        try:
            with open(path, "rb") as f:
                content = f.read()

            existing_raw_pdf = (
                await db.execute(
                    select(RawPdf.id).where(
                        RawPdf.user_id == user_id,
                        RawPdf.file_hash_sha256 == file_hash,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if existing_raw_pdf and not force_reprocess:
                artifact.status = "skipped"
                artifact.parse_message = (
                    "Duplicate statement hash; set force_reprocess=true to parse again"
                )
                artifact.processed_at = datetime.now(timezone.utc)
                result.skipped += 1
                continue

            pdf_id = uuid.uuid4()
            storage_dir = os.path.join(settings.upload_dir, str(user_id))
            os.makedirs(storage_dir, exist_ok=True)
            storage_path = os.path.join(storage_dir, f"{pdf_id}.pdf")
            with open(storage_path, "wb") as out:
                out.write(content)

            raw_pdf = RawPdf(
                id=pdf_id,
                user_id=user_id,
                source_type="folder_reprocess" if existing_raw_pdf else "folder_import",
                original_filename=path.name,
                file_hash_sha256=file_hash,
                storage_path=storage_path,
                file_size_bytes=size_bytes,
                is_password_protected=False,
            )
            db.add(raw_pdf)
            await db.flush()

            password = _password_for_path(str(path), password_map)
            try:
                await ingest_pdf_knowledge(
                    db=db,
                    user_id=user_id,
                    pdf_content=content,
                    password=password,
                    source_filename=path.name,
                    source_kind="raw_pdf",
                    raw_pdf_id=pdf_id,
                    bank_hint=classified.bank_hint,
                    account_type_hint=(
                        "credit_card" if classified.doc_type == "credit_card_statement" else None
                    ),
                    doc_type=classified.doc_type,
                )
            except Exception:
                pass
            try:
                statement = await parse_statement(
                    db=db,
                    user_id=user_id,
                    pdf_id=pdf_id,
                    pdf_content=content,
                    password=password,
                    bank_hint=classified.bank_hint,
                    allow_semantic_duplicate=force_reprocess,
                )
            except StatementDuplicateError as dup_exc:
                await db.execute(
                    delete(DocumentKnowledgeChunk).where(
                        DocumentKnowledgeChunk.user_id == user_id,
                        DocumentKnowledgeChunk.raw_pdf_id == pdf_id,
                    )
                )
                await db.execute(
                    delete(RawPdf).where(
                        RawPdf.id == pdf_id,
                        RawPdf.user_id == user_id,
                    )
                )
                try:
                    if os.path.exists(storage_path):
                        os.remove(storage_path)
                except OSError:
                    pass
                artifact.status = "skipped"
                artifact.parse_message = str(dup_exc)
                artifact.processed_at = datetime.now(timezone.utc)
                result.skipped += 1
                continue
            tx_count = statement.transaction_count or 0
            if tx_count > 0:
                if classified.doc_type == "unknown_pdf":
                    artifact.doc_type = (
                        "credit_card_statement"
                        if statement.account_type == "credit_card"
                        else "bank_statement"
                    )
                    artifact.bank_hint = statement.bank_name or artifact.bank_hint
                artifact.status = "parsed"
                artifact.parse_message = (
                    f"Parsed {tx_count} transactions using {statement.parser_used}"
                )
                result.parsed += 1
            else:
                artifact.status = "skipped"
                artifact.parse_message = (
                    f"Parser {statement.parser_used} extracted 0 transactions. "
                    "Registered statement metadata for manual review."
                )
                result.skipped += 1
            artifact.metadata_json = {
                **(artifact.metadata_json or {}),
                "statement_id": str(statement.id),
                "parser_used": statement.parser_used,
            }
            artifact.processed_at = datetime.now(timezone.utc)
        except Exception as exc:
            if classified.doc_type == "unknown_pdf":
                artifact.status = "skipped"
                artifact.parse_message = (
                    "Unknown PDF could not be parsed as statement. "
                    f"Reason: {exc}"
                )
                artifact.processed_at = datetime.now(timezone.utc)
                result.skipped += 1
            else:
                artifact.status = "failed"
                artifact.parse_message = str(exc)
                artifact.processed_at = datetime.now(timezone.utc)
                result.failed += 1
                result.messages.append(f"{path.name}: {exc}")

    if parse_supported and not dry_run and result.parsed > 0:
        auto = await reclassify_transfer_payments_for_user(
            db=db,
            user_id=user_id,
            days=3650,
            limit=10000,
            max_gap_days=7,
            use_llm=True,
        )
        result.messages.append(
            "Auto-reclassify completed: "
            f"updated={auto.updated}, card_pairs={auto.matched_credit_card_pairs}, "
            f"llm_promoted={auto.llm_promoted}"
        )

    return result


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _password_for_path(path: str, password_map: dict[str, str] | None) -> str | None:
    if not password_map:
        return None
    lower = path.lower()
    for key, password in password_map.items():
        if key.lower() in lower and password:
            return password
    return None


def _should_attempt_unknown_pdf_parse(path: Path, bank_hint: str | None) -> bool:
    if bank_hint:
        return True
    text = path.name.lower().replace("_", " ").replace("-", " ")
    keywords = (
        "statement",
        "stmt",
        "passbook",
        "account",
        "a/c",
        "credit card",
        "card",
        "txn",
        "transaction",
    )
    return any(k in text for k in keywords)


def _validate_path_allowed(path: Path) -> None:
    if not settings.local_only_mode:
        return

    allowed_roots = [Path(p).expanduser().resolve() for p in settings.parsed_local_roots()]
    if any(path.is_relative_to(root) for root in allowed_roots):
        return
    raise ValueError(
        "Path is outside configured local roots. "
        f"Allowed roots: {[str(r) for r in allowed_roots]}"
    )


def _resolve_folder_path(path_input: str) -> Path:
    """Normalize user-provided folder path across Linux/macOS/Windows formats."""
    raw = (path_input or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("Folder path is required.")

    candidates = _path_candidates(raw)
    resolved_candidates: list[Path] = []
    for candidate in candidates:
        path_obj = Path(candidate).expanduser()
        try:
            resolved = path_obj.resolve(strict=False)
        except Exception:
            continue
        resolved_candidates.append(resolved)
        if resolved.exists():
            return resolved

    if resolved_candidates:
        return resolved_candidates[0]
    return Path(raw).expanduser().resolve(strict=False)


def _path_candidates(raw: str) -> list[str]:
    out: list[str] = []

    def add(value: str | None) -> None:
        if not value:
            return
        normalized = value.strip()
        if not normalized:
            return
        if normalized not in out:
            out.append(normalized)

    add(raw)

    if raw.lower().startswith("file://"):
        parsed = urlparse(raw)
        candidate = unquote(parsed.path or "")
        if parsed.netloc and not candidate.startswith("/"):
            candidate = f"/{parsed.netloc}/{candidate}"
        add(candidate)

    add(raw.replace("\\", "/"))

    # Convert Windows drive path (C:\foo\bar or C:/foo/bar) to common POSIX mounts.
    windows_drive_match = re.match(r"^([a-zA-Z]):[\\/](.*)$", raw)
    if windows_drive_match:
        drive = windows_drive_match.group(1).lower()
        tail = windows_drive_match.group(2).replace("\\", "/")
        add(f"/mnt/{drive}/{tail}")
        add(f"/{drive}/{tail}")

    # macOS path fallback for Linux hosts with mirrored home directories.
    mac_user_match = re.match(r"^/Users/([^/]+)/(.*)$", raw.replace("\\", "/"))
    if mac_user_match:
        user = mac_user_match.group(1)
        tail = mac_user_match.group(2)
        add(f"/home/{user}/{tail}")
        add(str(Path.home() / tail))

    return out
