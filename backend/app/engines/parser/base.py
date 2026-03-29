"""Statement parser engine — base class, registry, and orchestrator."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ledger.fingerprint import (
    build_statement_semantic_fingerprint,
    build_transaction_dedupe_fingerprint,
)
from app.engines.parser.hints import (
    infer_account_type_hint_from_text,
    infer_bank_hint_from_text,
    normalize_parser_hints,
)
from app.models.parsed_transaction import ParsedTransaction
from app.models.raw_pdf import RawPdf
from app.models.statement import Statement

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class StatementDuplicateError(ValueError):
    """Raised when a semantic duplicate statement already exists for the user."""

    pass


@dataclass
class ExtractedTransaction:
    """A single transaction extracted from a statement."""

    transaction_date: date
    posting_date: date | None
    description: str
    amount: float
    direction: str  # 'debit' | 'credit'
    reference_number: str | None = None
    foreign_amount: float | None = None
    foreign_currency: str | None = None
    confidence: float = 1.0
    line_number: int | None = None


@dataclass
class ExtractedStatement:
    """Full parsed statement output."""

    bank_name: str
    account_type: str  # 'credit_card' | 'savings' | 'current'
    account_number_masked: str | None = None
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    due_date: date | None = None
    min_amount_due: float | None = None
    total_amount_due: float | None = None
    credit_limit: float | None = None
    available_limit: float | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    previous_balance: float | None = None
    payments_received: float | None = None
    transactions: list[ExtractedTransaction] = field(default_factory=list)
    parser_id: str = ""
    warnings: list[str] = field(default_factory=list)


class StatementParser(ABC):
    """Abstract base class for bank-specific statement parsers."""

    @property
    @abstractmethod
    def parser_id(self) -> str:
        """Unique identifier, e.g. 'hdfc_cc_v1'."""
        ...

    @property
    @abstractmethod
    def bank_name(self) -> str:
        """Bank name, e.g. 'HDFC'."""
        ...

    @property
    @abstractmethod
    def account_type(self) -> str:
        """'credit_card' | 'savings' | 'current'."""
        ...

    @abstractmethod
    def detect(self, text: str) -> bool:
        """Return True if this parser can handle the given PDF text."""
        ...

    @abstractmethod
    def parse(self, pages: list[str], full_text: str) -> ExtractedStatement:
        """Parse pages of text into an ExtractedStatement."""
        ...


# ─── Parser Registry ───────────────────────────────────

_registry: list[StatementParser] = []


def register_parser(parser: StatementParser) -> None:
    _registry.append(parser)


def detect_parser(
    text: str,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
) -> StatementParser | None:
    """Find the right parser for a given PDF text.

    If bank_hint is provided, prefer parsers matching that bank.
    """
    hints = normalize_parser_hints(bank_hint=bank_hint, account_type_hint=account_type_hint)
    bank_hint = hints.bank_hint
    account_type_hint = hints.account_type_hint
    candidates = []
    for parser in _registry:
        if parser.detect(text):
            candidates.append(parser)

    def _matches_account_type(parser: StatementParser) -> bool:
        if not account_type_hint or account_type_hint == "auto":
            return True
        if account_type_hint == "credit_card":
            return parser.account_type == "credit_card"
        if account_type_hint == "bank_account":
            return parser.account_type != "credit_card"
        return parser.account_type == account_type_hint

    if not candidates:
        if bank_hint:
            hinted = [p for p in _registry if p.bank_name.upper() == bank_hint.upper()]
            if hinted:
                hinted = [parser for parser in hinted if _matches_account_type(parser)] or hinted
                if account_type_hint == "credit_card":
                    for parser in hinted:
                        if parser.account_type == "credit_card":
                            return parser
                if account_type_hint == "bank_account":
                    for parser in hinted:
                        if parser.account_type != "credit_card":
                            return parser
                # If bank has both savings/credit-card parsers, choose by card cues.
                has_card_cues = "credit card" in text.lower() or "card statement" in text.lower()
                preferred_type = "credit_card" if has_card_cues else "savings"
                for parser in hinted:
                    if parser.account_type == preferred_type:
                        return parser
                return hinted[0]
        return None

    filtered = [candidate for candidate in candidates if _matches_account_type(candidate)]
    if filtered:
        candidates = filtered

    if bank_hint and len(candidates) > 1:
        for c in candidates:
            if c.bank_name.upper() == bank_hint.upper():
                return c

    return candidates[0]


def get_registered_parsers() -> list[StatementParser]:
    return list(_registry)


# ─── Orchestrator ──────────────────────────────────────

async def parse_statement(
    db: AsyncSession,
    user_id: uuid.UUID,
    pdf_id: uuid.UUID,
    pdf_content: bytes,
    password: str | None = None,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    prefer_llm: bool = False,
    allow_semantic_duplicate: bool = False,
) -> Statement:
    """Main entry point: decrypt PDF, detect parser, extract data, save to DB."""
    from app.config import settings
    from app.engines.parser.pdf_utils import decrypt_pdf, extract_text

    # Ensure parsers are registered
    _ensure_parsers_loaded()

    # Step 1: Decrypt if needed
    try:
        pdf_bytes = decrypt_pdf(pdf_content, password)
    except ValueError:
        raise
    except Exception as exc:
        logger.error("PDF decryption failed for pdf_id=%s: %s", pdf_id, exc)
        raise ValueError(
            f"Failed to process PDF: {exc}. "
            "If the PDF is password-protected, please provide the correct password."
        ) from exc

    # Step 2: Extract text
    pages = extract_text(pdf_bytes)
    if not pages or all(not p.strip() for p in pages):
        logger.warning(
            "No text extracted from PDF pdf_id=%s (pages=%d). "
            "File may be scanned/image-based or corrupted.",
            pdf_id,
            len(pages),
        )
        raise ValueError(
            "Could not extract text from PDF. The file may be scanned (image-based), "
            "corrupted, or in a format that is not supported. "
            "Scanned PDFs require OCR which is not yet supported."
        )

    full_text = "\n".join(pages)
    text_bank_hint = infer_bank_hint_from_text(full_text)
    text_account_type_hint = infer_account_type_hint_from_text(full_text)

    # Log first 500 chars for debugging
    text_preview = full_text[:500].replace("\n", "\\n")
    logger.info(
        "PDF text extracted for pdf_id=%s: %d pages, %d chars. Preview: %s",
        pdf_id,
        len(pages),
        len(full_text),
        text_preview,
    )

    # Step 3: Detect parser
    hints = normalize_parser_hints(bank_hint=bank_hint, account_type_hint=account_type_hint)
    bank_hint = hints.bank_hint or text_bank_hint
    account_type_hint = hints.account_type_hint or text_account_type_hint
    knowledge_context = None
    llm_client = None
    llm_classification = None
    if settings.llm_enabled:
        from app.engines.llm.client import LLMClient
        from app.engines.llm.knowledge import build_statement_knowledge_context
        from app.engines.llm.statement_classifier import llm_classify_statement

        llm_client = LLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        knowledge_context = await build_statement_knowledge_context(
            db=db,
            user_id=user_id,
            current_text=full_text,
            bank_hint=bank_hint,
            account_type_hint=account_type_hint,
            exclude_raw_pdf_id=pdf_id,
        )
        if hints.bank_hint is None or hints.account_type_hint is None:
            llm_classification = await llm_classify_statement(
                llm_client,
                full_text,
                knowledge_context=knowledge_context,
                bank_hint=bank_hint,
                account_type_hint=account_type_hint,
            )
            if llm_classification and llm_classification.confidence >= 0.55:
                bank_hint = hints.bank_hint or llm_classification.bank_name or bank_hint
                if hints.account_type_hint is None:
                    if llm_classification.account_type == "credit_card":
                        account_type_hint = "credit_card"
                    elif llm_classification.account_type in {"savings", "current"}:
                        account_type_hint = "bank_account"

    parser = detect_parser(full_text, bank_hint, account_type_hint)
    extracted: ExtractedStatement
    if prefer_llm and settings.llm_enabled:
        from app.engines.llm.parse_fallback import llm_parse_statement

        llm_result = await llm_parse_statement(
            llm_client,
            full_text,
            bank_hint=bank_hint,
            account_type_hint=account_type_hint,
            knowledge_context=knowledge_context,
        )
        if llm_result and llm_result.transactions:
            llm_result.parser_id = "llm_rereview"
            llm_result.warnings.append("Statement was re-reviewed through the local LLM.")
            extracted = llm_result
            parser = None
        else:
            logger.warning(
                "Preferred LLM re-review produced no valid transactions for pdf_id=%s; falling back to parser detection.",
                pdf_id,
            )
            parser = detect_parser(full_text, bank_hint, account_type_hint)
    else:
        extracted = None  # type: ignore[assignment]
    if parser is None and not prefer_llm:
        registered = [f"{p.bank_name}/{p.account_type}" for p in get_registered_parsers()]
        logger.warning(
            "No parser matched for pdf_id=%s (bank_hint=%s). "
            "Registered parsers: %s. Text preview: %s",
            pdf_id,
            bank_hint,
            registered,
            text_preview,
        )
        if settings.llm_enabled:
            logger.info("No template parser matched; attempting direct LLM parse for pdf_id=%s", pdf_id)
            try:
                from app.engines.llm.parse_fallback import llm_parse_statement

                llm_result = await llm_parse_statement(
                    llm_client,
                    full_text,
                    bank_hint=bank_hint,
                    account_type_hint=account_type_hint,
                    knowledge_context=knowledge_context,
                )
            except Exception as exc:
                raise ValueError(
                    "Could not identify the bank/statement type and LLM fallback failed: "
                    f"{exc}. Supported template formats: {', '.join(registered)}."
                ) from exc

            if not llm_result or not llm_result.transactions:
                raise ValueError(
                    "Could not identify the bank/statement type. "
                    f"Supported template formats: {', '.join(registered)}. "
                    "LLM fallback also could not extract transactions."
                )
            if (
                bank_hint
                and (not llm_result.bank_name or llm_result.bank_name.lower() == "unknown")
            ):
                llm_result.bank_name = bank_hint.upper()
            if account_type_hint == "credit_card":
                llm_result.account_type = "credit_card"
            elif account_type_hint == "bank_account" and llm_result.account_type == "credit_card":
                llm_result.account_type = "savings"
            elif llm_result.account_type not in {"credit_card", "savings", "current"}:
                llm_result.account_type = "savings"
            llm_result.parser_id = "llm_fallback_direct"
            llm_result.warnings.append("No template parser matched; parsed via local LLM fallback.")
            extracted = llm_result
        else:
            raise ValueError(
                "Could not identify the bank/statement type. "
                f"Supported formats: {', '.join(registered)}. "
                "Try specifying a bank_hint or check that this statement format is supported."
            )
    else:
        if prefer_llm and 'extracted' in locals() and extracted is not None:
            logger.info(
                "LLM re-review selected for pdf_id=%s: parser=%s, transactions=%d",
                pdf_id,
                extracted.parser_id,
                len(extracted.transactions),
            )
        elif parser is None:
            raise ValueError("Could not parse statement during local LLM re-review.")
        else:
            logger.info(
                "Parser detected for pdf_id=%s: %s (%s/%s)",
                pdf_id,
                parser.parser_id,
                parser.bank_name,
                parser.account_type,
            )

            # Step 4: Parse
            try:
                extracted = parser.parse(pages, full_text)
            except Exception as exc:
                logger.error(
                    "Parser %s crashed for pdf_id=%s: %s",
                    parser.parser_id,
                    pdf_id,
                    exc,
                    exc_info=True,
                )
                raise ValueError(
                    f"Parser '{parser.parser_id}' failed to process this statement: {exc}. "
                    "The PDF format may have changed. Please report this issue."
                ) from exc

            logger.info(
                "Parser %s extracted %d transactions for pdf_id=%s (metadata: period=%s..%s, account=%s)",
                parser.parser_id,
                len(extracted.transactions),
                pdf_id,
                extracted.statement_period_start,
                extracted.statement_period_end,
                extracted.account_number_masked,
            )

            # Step 4b: LLM fallback if template returned 0 transactions.
            if not extracted.transactions:
                logger.warning(
                    "Template parser %s returned 0 transactions for pdf_id=%s. "
                    "LLM_ENABLED=%s. Text preview: %s",
                    parser.parser_id,
                    pdf_id,
                    settings.llm_enabled,
                    text_preview,
                )

                if settings.llm_enabled:
                    logger.info("Attempting LLM fallback for pdf_id=%s", pdf_id)
                    try:
                        from app.engines.llm.parse_fallback import llm_parse_statement

                        llm_result = await llm_parse_statement(
                            llm_client,
                            full_text,
                            bank_hint=bank_hint or extracted.bank_name,
                            account_type_hint=account_type_hint,
                            knowledge_context=knowledge_context,
                        )
                        if llm_result and llm_result.transactions:
                            logger.info(
                                "LLM fallback extracted %d transactions for pdf_id=%s",
                                len(llm_result.transactions),
                                pdf_id,
                            )
                            extracted.transactions = llm_result.transactions
                            extracted.parser_id = f"{extracted.parser_id}+llm_fallback"
                            extracted.warnings.append(
                                f"Template parser found 0 transactions; "
                                f"LLM fallback extracted {len(llm_result.transactions)}. "
                                f"Review recommended."
                            )
                            # Inherit metadata from LLM if template didn't find any.
                            if not extracted.account_number_masked and llm_result.account_number_masked:
                                extracted.account_number_masked = llm_result.account_number_masked
                            if not extracted.statement_period_start and llm_result.statement_period_start:
                                extracted.statement_period_start = llm_result.statement_period_start
                                extracted.statement_period_end = llm_result.statement_period_end
                            if not extracted.due_date and llm_result.due_date:
                                extracted.due_date = llm_result.due_date
                            if not extracted.total_amount_due and llm_result.total_amount_due:
                                extracted.total_amount_due = llm_result.total_amount_due
                            if not extracted.min_amount_due and llm_result.min_amount_due:
                                extracted.min_amount_due = llm_result.min_amount_due
                            if not extracted.previous_balance and llm_result.previous_balance:
                                extracted.previous_balance = llm_result.previous_balance
                            if not extracted.payments_received and llm_result.payments_received:
                                extracted.payments_received = llm_result.payments_received
                            if not extracted.opening_balance and llm_result.opening_balance:
                                extracted.opening_balance = llm_result.opening_balance
                            if not extracted.closing_balance and llm_result.closing_balance:
                                extracted.closing_balance = llm_result.closing_balance
                        else:
                            logger.warning(
                                "LLM fallback also returned 0 transactions for pdf_id=%s",
                                pdf_id,
                            )
                            extracted.warnings.append(
                                "Template parser and LLM fallback both found 0 transactions. "
                                "The statement format may not be supported or the text extraction failed."
                            )
                    except Exception as exc:
                        logger.error(
                            "LLM fallback failed for pdf_id=%s: %s",
                            pdf_id,
                            exc,
                            exc_info=True,
                        )
                        extracted.warnings.append(f"LLM fallback failed: {exc}")
                else:
                    extracted.warnings.append(
                        "Template parser found 0 transactions and LLM fallback is disabled. "
                        "Enable LLM_ENABLED=true in configuration to try AI-based extraction."
                    )

    semantic_fingerprint = build_statement_semantic_fingerprint(
        user_id=user_id,
        institution_name=extracted.bank_name,
        account_masked=extracted.account_number_masked,
        period_start=extracted.statement_period_start,
        period_end=extracted.statement_period_end,
        opening_balance=extracted.opening_balance,
    )
    superseded_statement: Statement | None = None
    if semantic_fingerprint:
        existing_active = (
            await db.execute(
                select(Statement)
                .where(
                    Statement.user_id == user_id,
                    Statement.is_active == True,  # noqa: E712
                    Statement.statement_fingerprint == semantic_fingerprint,
                )
                .order_by(desc(Statement.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing_active is not None and not allow_semantic_duplicate:
            raise StatementDuplicateError(
                "This statement already exists (semantic duplicate detected for bank/account/period)."
            )
        if existing_active is not None and allow_semantic_duplicate:
            superseded_statement = existing_active

    # Step 5-7: Persist atomically so partial promotion cannot leak.
    from app.engines.insights.bill_tracker import create_bill_from_statement
    from app.engines.ledger.merger import promote_to_canonical

    async with db.begin_nested():
        raw_pdf = await db.get(RawPdf, pdf_id)
        if raw_pdf is not None:
            raw_pdf.semantic_fingerprint = semantic_fingerprint
        if superseded_statement is not None:
            superseded_statement.is_active = False

        parse_status = "parsed" if extracted.transactions else "partial"
        statement = Statement(
            user_id=user_id,
            pdf_id=pdf_id,
            bank_name=extracted.bank_name,
            account_type=extracted.account_type,
            account_number_masked=extracted.account_number_masked,
            statement_period_start=extracted.statement_period_start,
            statement_period_end=extracted.statement_period_end,
            due_date=extracted.due_date,
            min_amount_due=extracted.min_amount_due,
            total_amount_due=extracted.total_amount_due,
            credit_limit=extracted.credit_limit,
            available_limit=extracted.available_limit,
            opening_balance=extracted.opening_balance,
            closing_balance=extracted.closing_balance,
            previous_balance=extracted.previous_balance,
            payments_received=extracted.payments_received,
            parser_used=extracted.parser_id,
            parse_status=parse_status,
            statement_fingerprint=semantic_fingerprint,
            version_no=(superseded_statement.version_no + 1) if superseded_statement else 1,
            supersedes_statement_id=superseded_statement.id if superseded_statement else None,
            is_active=True,
            parsed_at=datetime.now(timezone.utc),
            transaction_count=len(extracted.transactions),
        )
        db.add(statement)
        await db.flush()

        for txn in extracted.transactions:
            extraction_method = "llm_fallback" if "+llm" in extracted.parser_id else "template"
            parsed = ParsedTransaction(
                user_id=user_id,
                source_type="statement",
                source_id=statement.id,
                statement_id=statement.id,
                transaction_date=txn.transaction_date,
                posting_date=txn.posting_date,
                description_raw=txn.description,
                amount=txn.amount,
                direction=txn.direction,
                currency="INR",
                foreign_amount=txn.foreign_amount,
                foreign_currency=txn.foreign_currency,
                reference_number=txn.reference_number,
                confidence=txn.confidence,
                extraction_method=extraction_method,
                line_number=txn.line_number,
                dedupe_fingerprint=build_transaction_dedupe_fingerprint(
                    user_id=user_id,
                    account_masked=extracted.account_number_masked,
                    transaction_date=txn.transaction_date,
                    amount=txn.amount,
                    description=txn.description,
                ),
            )
            db.add(parsed)
            await db.flush()

            await promote_to_canonical(
                db=db,
                user_id=user_id,
                parsed_txn=parsed,
                bank_name=extracted.bank_name,
                account_type=extracted.account_type,
                account_masked=extracted.account_number_masked,
            )

        await create_bill_from_statement(db, user_id, statement)

    logger.info(
        "Statement parsing complete for pdf_id=%s: parser=%s, transactions=%d, status=%s",
        pdf_id,
        extracted.parser_id,
        len(extracted.transactions),
        parse_status,
    )

    return statement


_parsers_loaded = False


def _ensure_parsers_loaded():
    global _parsers_loaded
    if _parsers_loaded:
        return
    _parsers_loaded = True
    # Import all templates to trigger registration
    from app.engines.parser.templates import (  # noqa: F401
        hdfc_cc,
        hdfc_savings,
        axis_cc,
        axis_savings,
        sbi_cc,
        sbi_savings,
    )
