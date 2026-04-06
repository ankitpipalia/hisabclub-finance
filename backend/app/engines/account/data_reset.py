from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.bill import Bill
from app.models.balance_snapshot import BalanceSnapshot
from app.models.budget import Budget
from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.connected_account import ConnectedAccount
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.document_artifact import DocumentArtifact
from app.models.document_knowledge_chunk import DocumentKnowledgeChunk
from app.models.extraction_job import ExtractionJob
from app.models.insights import MonthlySummary, RecurringPattern
from app.models.institution_password_pattern import InstitutionPasswordPattern
from app.models.parsed_transaction import ParsedTransaction
from app.models.password_reset_token import PasswordResetToken
from app.models.raw_pdf import RawPdf
from app.models.raw_sms import RawSms
from app.models.review_task import ReviewTask
from app.models.statement import Statement
from app.models.statement_period_coverage import StatementPeriodCoverage
from app.models.sync_cursor import SyncCursor
from app.models.tax_portal_data import TaxPortalData
from app.models.transaction_annotation import TransactionAnnotation
from app.models.transaction_source import TransactionSource
from app.models.transaction_split import TransactionSplit
from app.models.transfer_match import TransferMatch
from app.models.user_override import UserMerchantRule, UserOverride


@dataclass
class UserDataResetResult:
    deleted_rows: dict[str, int]
    deleted_files: int
    deleted_directories: int
    file_delete_errors: int


@dataclass
class _ResetPlan:
    deleted_rows: dict[str, int]
    file_paths: list[Path]
    user_dirs: list[Path]


def _safe_rowcount(value: int | None) -> int:
    if value is None:
        return 0
    return value if value > 0 else 0


async def clear_user_data_everywhere(db: AsyncSession, *, user_id: uuid.UUID) -> UserDataResetResult:
    plan = await _delete_user_rows(db, user_id=user_id)

    deleted_files = 0
    deleted_directories = 0
    file_delete_errors = 0

    for path in plan.file_paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            path.unlink()
            deleted_files += 1
        except OSError:
            file_delete_errors += 1

    for directory in plan.user_dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        try:
            shutil.rmtree(directory)
            deleted_directories += 1
        except OSError:
            file_delete_errors += 1

    return UserDataResetResult(
        deleted_rows=plan.deleted_rows,
        deleted_files=deleted_files,
        deleted_directories=deleted_directories,
        file_delete_errors=file_delete_errors,
    )


async def _delete_user_rows(db: AsyncSession, *, user_id: uuid.UUID) -> _ResetPlan:
    deleted_rows: dict[str, int] = {}

    raw_pdf_rows = (
        await db.execute(
            select(RawPdf.storage_path, RawPdf.cold_storage_path).where(RawPdf.user_id == user_id)
        )
    ).all()
    artifact_rows = (
        await db.execute(select(DocumentArtifact.file_path).where(DocumentArtifact.user_id == user_id))
    ).all()

    file_paths: list[Path] = []
    for hot_path, cold_path in raw_pdf_rows:
        if hot_path:
            file_paths.append(Path(hot_path))
        if cold_path:
            file_paths.append(Path(cold_path))
    for (artifact_path,) in artifact_rows:
        if artifact_path:
            file_paths.append(Path(artifact_path))

    user_dirs = [
        Path(settings.upload_dir).expanduser() / str(user_id),
        Path(settings.cold_storage_dir).expanduser() / str(user_id),
    ]

    async def run_delete(label: str, statement) -> None:
        result = await db.execute(statement)
        deleted_rows[label] = _safe_rowcount(result.rowcount)

    await run_delete(
        "review_task_resolutions_cleared",
        update(ReviewTask)
        .where(ReviewTask.resolved_by_user_id == user_id)
        .values(resolved_by_user_id=None),
    )

    await run_delete("password_reset_tokens", delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    await run_delete("sync_cursors", delete(SyncCursor).where(SyncCursor.user_id == user_id))
    await run_delete("connected_accounts", delete(ConnectedAccount).where(ConnectedAccount.user_id == user_id))
    await run_delete(
        "institution_password_patterns",
        delete(InstitutionPasswordPattern).where(InstitutionPasswordPattern.user_id == user_id),
    )
    await run_delete("user_merchant_rules", delete(UserMerchantRule).where(UserMerchantRule.user_id == user_id))
    await run_delete("user_overrides", delete(UserOverride).where(UserOverride.user_id == user_id))
    await run_delete("transfer_matches", delete(TransferMatch).where(TransferMatch.user_id == user_id))
    await run_delete("transaction_splits", delete(TransactionSplit).where(TransactionSplit.user_id == user_id))
    await run_delete(
        "statement_period_coverage",
        delete(StatementPeriodCoverage).where(StatementPeriodCoverage.user_id == user_id),
    )
    await run_delete("review_tasks", delete(ReviewTask).where(ReviewTask.user_id == user_id))
    await run_delete(
        "conversation_messages",
        delete(ConversationMessage).where(ConversationMessage.user_id == user_id),
    )
    await run_delete(
        "conversation_threads",
        delete(ConversationThread).where(ConversationThread.user_id == user_id),
    )
    await run_delete(
        "transaction_annotations",
        delete(TransactionAnnotation).where(TransactionAnnotation.user_id == user_id),
    )
    await run_delete("tax_portal_data", delete(TaxPortalData).where(TaxPortalData.user_id == user_id))
    await run_delete("extraction_jobs", delete(ExtractionJob).where(ExtractionJob.user_id == user_id))
    await run_delete(
        "document_knowledge_chunks",
        delete(DocumentKnowledgeChunk).where(DocumentKnowledgeChunk.user_id == user_id),
    )
    await run_delete("bills", delete(Bill).where(Bill.user_id == user_id))
    await run_delete("budgets", delete(Budget).where(Budget.user_id == user_id))
    await run_delete("monthly_summaries", delete(MonthlySummary).where(MonthlySummary.user_id == user_id))
    await run_delete("recurring_patterns", delete(RecurringPattern).where(RecurringPattern.user_id == user_id))
    await run_delete("balance_snapshots", delete(BalanceSnapshot).where(BalanceSnapshot.user_id == user_id))
    await run_delete("raw_sms", delete(RawSms).where(RawSms.user_id == user_id))

    canonical_ids_subquery = select(CanonicalTransaction.id).where(
        CanonicalTransaction.user_id == user_id
    )
    parsed_ids_subquery = select(ParsedTransaction.id).where(
        ParsedTransaction.user_id == user_id
    )
    await run_delete(
        "transaction_sources",
        delete(TransactionSource).where(
            or_(
                TransactionSource.canonical_txn_id.in_(canonical_ids_subquery),
                TransactionSource.parsed_txn_id.in_(parsed_ids_subquery),
            )
        ),
    )
    await run_delete("parsed_transactions", delete(ParsedTransaction).where(ParsedTransaction.user_id == user_id))

    await run_delete(
        "canonical_transactions",
        delete(CanonicalTransaction).where(CanonicalTransaction.user_id == user_id),
    )
    await run_delete("statements", delete(Statement).where(Statement.user_id == user_id))
    await run_delete("accounts", delete(Account).where(Account.user_id == user_id))
    await run_delete("raw_pdfs", delete(RawPdf).where(RawPdf.user_id == user_id))
    await run_delete("document_artifacts", delete(DocumentArtifact).where(DocumentArtifact.user_id == user_id))
    await run_delete("categories", delete(Category).where(Category.user_id == user_id))

    return _ResetPlan(
        deleted_rows=deleted_rows,
        file_paths=file_paths,
        user_dirs=user_dirs,
    )
