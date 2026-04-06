from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.account_labels import bank_account_label
from app.engines.ledger.category_enrichment import infer_uncategorized_category
from app.engines.ledger.transfer_reclassifier import reclassify_transfer_payments_for_user
from app.engines.ledger.upi_reconciliation import reconcile_upi_failures_for_user
from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.parsed_transaction import ParsedTransaction
from app.models.transaction_split import TransactionSplit
from app.models.transaction_source import TransactionSource
from app.models.user_override import UserOverride
from app.schemas.transaction import (
    AutoCategorizeResponse,
    ReclassifyTransferResponse,
    TransactionDetailResponse,
    TransactionBulkUpdateRequest,
    TransactionBulkUpdateResponse,
    TransactionListResponse,
    TransactionOverrideResponse,
    TransactionResponse,
    TransactionSplitRequest,
    TransactionSplitResponse,
    TransactionSourceResponse,
    TransactionUpdateRequest,
    UpiReconcileResponse,
)

router = APIRouter()

_ALLOWED_TRANSACTION_NATURES = {
    "expense",
    "income",
    "transfer_internal",
    "refund",
    "investment",
    "tax",
}


def _normalize_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    cleaned = [tag.strip() for tag in tags if tag and tag.strip()]
    return cleaned or None


def _quantize_amount(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _validate_category_id(db: DbSession, user_id, category_id: str | None) -> None:
    if category_id is None:
        return
    category = (
        await db.execute(
            select(Category).where(
                Category.id == category_id,
                (Category.user_id == user_id) | (Category.is_system == True),  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category_id.")


def _normalize_updates(request: TransactionUpdateRequest | TransactionBulkUpdateRequest) -> dict:
    updates = request.model_dump(exclude_unset=True)
    if "transaction_nature" in updates and updates["transaction_nature"] is not None:
        normalized_nature = str(updates["transaction_nature"]).strip().lower()
        if normalized_nature not in _ALLOWED_TRANSACTION_NATURES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction_nature.")
        updates["transaction_nature"] = normalized_nature
    if "tags" in updates:
        updates["tags"] = _normalize_tags(updates["tags"])
    if "notes" in updates and updates["notes"] is not None:
        updates["notes"] = str(updates["notes"]).strip() or None
    return updates


async def _apply_transaction_updates(db: DbSession, *, user_id, txn: CanonicalTransaction, updates: dict) -> None:
    for field, new_value in updates.items():
        old_value = getattr(txn, field, None)
        if old_value == new_value:
            continue
        db.add(
            UserOverride(
                user_id=user_id,
                canonical_txn_id=txn.id,
                field_name=field,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else "",
            )
        )
        setattr(txn, field, new_value)
    if "category_id" in updates:
        txn.category_source = "user"

def _txn_to_response(t: CanonicalTransaction, category_name: str | None = None):
    return TransactionResponse(
        id=str(t.id),
        transaction_date=t.transaction_date,
        posting_date=t.posting_date,
        amount=float(t.amount),
        direction=t.direction,
        transaction_nature=t.transaction_nature,
        currency=t.currency,
        merchant_raw=t.merchant_raw,
        merchant_normalized=t.merchant_normalized,
        category_id=str(t.category_id) if t.category_id else None,
        category_name=category_name,
        bank_name=t.bank_name,
        bank_label=bank_account_label(t.bank_name, t.account_type),
        account_type=t.account_type,
        account_masked=t.account_masked,
        is_recurring=t.is_recurring,
        is_anomalous=t.is_anomalous,
        is_excluded=t.is_excluded,
        notes=t.notes,
        tags=t.tags,
        created_at=t.created_at,
    )


@router.post("/auto-categorize-uncategorized", response_model=AutoCategorizeResponse)
async def auto_categorize_uncategorized(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(300, ge=1, le=2000),
):
    rows = (
        await db.execute(
            select(CanonicalTransaction)
            .where(CanonicalTransaction.user_id == user.id)
            .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
            .where(CanonicalTransaction.category_id.is_(None))
            .order_by(
                CanonicalTransaction.transaction_date.desc(),
                CanonicalTransaction.created_at.desc(),
            )
            .limit(limit)
        )
    ).scalars().all()

    updated = 0
    for txn in rows:
        category_id, category_source = await infer_uncategorized_category(
            db=db,
            user_id=user.id,
            description_raw=txn.merchant_raw,
            amount=float(txn.amount),
        )
        if category_id is None:
            continue
        txn.category_id = category_id
        txn.category_source = category_source
        updated += 1

    if updated > 0:
        await db.commit()

    return AutoCategorizeResponse(scanned=len(rows), updated=updated)


@router.post("/reclassify-transfer-payments", response_model=ReclassifyTransferResponse)
async def reclassify_transfer_payments(
    user: CurrentUser,
    db: DbSession,
    days: int = Query(365, ge=30, le=3650),
    limit: int = Query(3000, ge=100, le=10000),
    max_gap_days: int = Query(7, ge=0, le=21),
    use_llm: bool = Query(True),
):
    result = await reclassify_transfer_payments_for_user(
        db=db,
        user_id=user.id,
        days=days,
        limit=limit,
        max_gap_days=max_gap_days,
        use_llm=use_llm,
    )
    if result.updated > 0:
        await db.commit()

    return ReclassifyTransferResponse(
        scanned=result.scanned,
        updated=result.updated,
        matched_credit_card_pairs=result.matched_credit_card_pairs,
        llm_checked=result.llm_checked,
        llm_promoted=result.llm_promoted,
    )


@router.post("/reconcile-upi-failures", response_model=UpiReconcileResponse)
async def reconcile_upi_failures(
    user: CurrentUser,
    db: DbSession,
    days: int = Query(365, ge=30, le=3650),
    max_gap_days: int = Query(3, ge=0, le=10),
    limit: int = Query(5000, ge=100, le=20000),
):
    result = await reconcile_upi_failures_for_user(
        db=db,
        user_id=user.id,
        days=days,
        max_gap_days=max_gap_days,
        limit=limit,
    )
    if result.updated_transactions > 0:
        await db.commit()
    return UpiReconcileResponse(
        scanned=result.scanned,
        matched_pairs=result.matched_pairs,
        updated_transactions=result.updated_transactions,
    )


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    user: CurrentUser,
    db: DbSession,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    category_id: str | None = Query(None),
    bank: str | None = Query(None),
    direction: str | None = Query(None),
    nature: str | None = Query(None),
    min_amount: float | None = Query(None),
    max_amount: float | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    query = (
        select(CanonicalTransaction)
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(CanonicalTransaction.user_id == user.id)
        .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
    )

    if date_from:
        query = query.where(CanonicalTransaction.transaction_date >= date_from)
    if date_to:
        query = query.where(CanonicalTransaction.transaction_date <= date_to)
    if category_id:
        query = query.where(CanonicalTransaction.category_id == category_id)
    if bank:
        query = query.where(CanonicalTransaction.bank_name == bank.upper())
    if direction:
        query = query.where(CanonicalTransaction.direction == direction.lower())
    if nature:
        query = query.where(CanonicalTransaction.transaction_nature == nature.lower())
    if min_amount is not None:
        query = query.where(CanonicalTransaction.amount >= min_amount)
    if max_amount is not None:
        query = query.where(CanonicalTransaction.amount <= max_amount)
    if search:
        query = query.where(
            CanonicalTransaction.merchant_raw.ilike(f"%{search}%")
            | CanonicalTransaction.merchant_normalized.ilike(f"%{search}%")
            | CanonicalTransaction.notes.ilike(f"%{search}%")
        )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(CanonicalTransaction.transaction_date.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    # Add category name
    query = query.add_columns(Category.name.label("category_name"))

    result = await db.execute(query)
    rows = result.all()

    return TransactionListResponse(
        items=[_txn_to_response(row[0], category_name=row[1]) for row in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{txn_id}", response_model=TransactionResponse)
async def get_transaction(txn_id: str, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(CanonicalTransaction, Category.name.label("category_name"))
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(CanonicalTransaction.id == txn_id, CanonicalTransaction.user_id == user.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _txn_to_response(row[0], category_name=row[1])


@router.get("/{txn_id}/detail", response_model=TransactionDetailResponse)
async def get_transaction_detail(txn_id: str, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(CanonicalTransaction, Category.name.label("category_name"))
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(CanonicalTransaction.id == txn_id, CanonicalTransaction.user_id == user.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    txn, category_name = row

    source_rows = (
        await db.execute(
            select(TransactionSource, ParsedTransaction)
            .join(ParsedTransaction, TransactionSource.parsed_txn_id == ParsedTransaction.id)
            .where(TransactionSource.canonical_txn_id == txn.id)
            .order_by(TransactionSource.is_primary.desc(), ParsedTransaction.confidence.desc())
        )
    ).all()
    sources = [
        TransactionSourceResponse(
            parsed_txn_id=str(parsed.id),
            statement_id=str(parsed.statement_id) if parsed.statement_id else None,
            source_type=parsed.source_type,
            description_raw=parsed.description_raw,
            confidence=parsed.confidence,
            extraction_method=parsed.extraction_method,
            match_method=source.match_method,
            is_primary=source.is_primary,
        )
        for source, parsed in source_rows
    ]

    override_rows = (
        await db.execute(
            select(UserOverride)
            .where(
                UserOverride.user_id == user.id,
                UserOverride.canonical_txn_id == txn.id,
            )
            .order_by(UserOverride.created_at.desc())
        )
    ).scalars().all()
    overrides = [
        TransactionOverrideResponse(
            id=str(item.id),
            field_name=item.field_name,
            old_value=item.old_value,
            new_value=item.new_value,
            override_reason=item.override_reason,
            created_at=item.created_at,
        )
        for item in override_rows
    ]

    split_parent_row = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .join(
                TransactionSplit,
                TransactionSplit.source_canonical_txn_id == CanonicalTransaction.id,
            )
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(
                TransactionSplit.user_id == user.id,
                TransactionSplit.child_canonical_txn_id == txn.id,
            )
        )
    ).one_or_none()
    split_parent = (
        _txn_to_response(split_parent_row[0], category_name=split_parent_row[1])
        if split_parent_row is not None
        else None
    )

    split_children_rows = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .join(
                TransactionSplit,
                TransactionSplit.child_canonical_txn_id == CanonicalTransaction.id,
            )
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(
                TransactionSplit.user_id == user.id,
                TransactionSplit.source_canonical_txn_id == txn.id,
            )
            .order_by(TransactionSplit.split_index.asc())
        )
    ).all()

    return TransactionDetailResponse(
        transaction=_txn_to_response(txn, category_name=category_name),
        sources=sources,
        overrides=overrides,
        split_parent=split_parent,
        split_children=[
            _txn_to_response(child, category_name=child_category_name)
            for child, child_category_name in split_children_rows
        ],
    )


@router.patch("/{txn_id}", response_model=TransactionResponse)
async def update_transaction(
    txn_id: str, request: TransactionUpdateRequest, user: CurrentUser, db: DbSession
):
    result = await db.execute(
        select(CanonicalTransaction).where(
            CanonicalTransaction.id == txn_id, CanonicalTransaction.user_id == user.id
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    updates = _normalize_updates(request)
    await _validate_category_id(db, user.id, updates.get("category_id"))
    await _apply_transaction_updates(db, user_id=user.id, txn=txn, updates=updates)

    await db.flush()

    # Re-fetch with category name
    result = await db.execute(
        select(CanonicalTransaction, Category.name.label("category_name"))
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(CanonicalTransaction.id == txn_id)
    )
    row = result.one()
    return _txn_to_response(row[0], category_name=row[1])


@router.post("/bulk-update", response_model=TransactionBulkUpdateResponse)
async def bulk_update_transactions(
    request: TransactionBulkUpdateRequest,
    user: CurrentUser,
    db: DbSession,
):
    txn_ids = [txn_id for txn_id in request.transaction_ids if txn_id]
    if not txn_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="transaction_ids are required.")

    updates = _normalize_updates(request)
    updates.pop("transaction_ids", None)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided.")

    await _validate_category_id(db, user.id, updates.get("category_id"))

    txns = (
        await db.execute(
            select(CanonicalTransaction)
            .where(CanonicalTransaction.user_id == user.id)
            .where(CanonicalTransaction.id.in_(txn_ids))
            .order_by(CanonicalTransaction.transaction_date.desc())
        )
    ).scalars().all()
    if len(txns) != len(set(txn_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more transactions were not found.",
        )

    for txn in txns:
        await _apply_transaction_updates(db, user_id=user.id, txn=txn, updates=updates)
    await db.flush()

    rows = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(CanonicalTransaction.id.in_([txn.id for txn in txns]))
            .order_by(CanonicalTransaction.transaction_date.desc())
        )
    ).all()
    return TransactionBulkUpdateResponse(
        updated_count=len(rows),
        items=[_txn_to_response(row[0], category_name=row[1]) for row in rows],
    )


@router.post("/{txn_id}/split", response_model=TransactionSplitResponse)
async def split_transaction(
    txn_id: str,
    request: TransactionSplitRequest,
    user: CurrentUser,
    db: DbSession,
):
    if len(request.parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least two split parts are required.",
        )

    txn = (
        await db.execute(
            select(CanonicalTransaction).where(
                CanonicalTransaction.id == txn_id,
                CanonicalTransaction.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if txn.is_excluded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Excluded transactions cannot be split.",
        )

    existing_split = (
        await db.execute(
            select(TransactionSplit).where(
                TransactionSplit.user_id == user.id,
                TransactionSplit.source_canonical_txn_id == txn.id,
            )
        )
    ).scalar_one_or_none()
    if existing_split is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This transaction has already been split.",
        )

    original_amount = _quantize_amount(txn.amount)
    part_sum = sum(_quantize_amount(part.amount) for part in request.parts)
    if part_sum != original_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Split parts must sum to the original amount ({original_amount}).",
        )

    created_children: list[CanonicalTransaction] = []
    for index, part in enumerate(request.parts):
        await _validate_category_id(db, user.id, part.category_id)
        part_amount = _quantize_amount(part.amount)
        if part_amount <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Split amounts must be positive.",
            )
        merchant_raw = (part.merchant_raw or txn.merchant_raw).strip()
        if not merchant_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each split part needs a description.",
            )
        transaction_nature = (part.transaction_nature or txn.transaction_nature or "expense").strip().lower()
        if transaction_nature not in _ALLOWED_TRANSACTION_NATURES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid transaction_nature.",
            )

        child = CanonicalTransaction(
            user_id=user.id,
            transaction_date=txn.transaction_date,
            posting_date=txn.posting_date,
            amount=float(part_amount),
            direction=txn.direction,
            currency=txn.currency,
            transaction_nature=transaction_nature,
            merchant_raw=merchant_raw,
            merchant_normalized=None,
            merchant_id=part.merchant_id or txn.merchant_id,
            category_id=part.category_id or txn.category_id,
            category_source="user" if part.category_id is not None else txn.category_source,
            account_masked=txn.account_masked,
            bank_name=txn.bank_name,
            account_type=txn.account_type,
            dedupe_fingerprint=None,
            foreign_amount=None,
            foreign_currency=None,
            is_recurring=False,
            is_anomalous=False,
            anomaly_reason=None,
            is_excluded=False,
            notes=(part.notes.strip() if part.notes else None),
            tags=_normalize_tags(part.tags) or txn.tags,
        )
        db.add(child)
        await db.flush()
        db.add(
            TransactionSplit(
                user_id=user.id,
                source_canonical_txn_id=txn.id,
                child_canonical_txn_id=child.id,
                split_index=index,
            )
        )
        created_children.append(child)

    if request.exclude_original:
        await _apply_transaction_updates(
            db,
            user_id=user.id,
            txn=txn,
            updates={"is_excluded": True},
        )

    await db.flush()

    created_rows = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(CanonicalTransaction.id.in_([child.id for child in created_children]))
            .order_by(CanonicalTransaction.created_at.asc())
        )
    ).all()
    original_row = (
        await db.execute(
            select(CanonicalTransaction, Category.name.label("category_name"))
            .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
            .where(CanonicalTransaction.id == txn.id)
        )
    ).one()

    return TransactionSplitResponse(
        original_transaction=_txn_to_response(original_row[0], category_name=original_row[1]),
        created_transactions=[_txn_to_response(row[0], category_name=row[1]) for row in created_rows],
    )


@router.get("/{txn_id}/sources", response_model=list[TransactionSourceResponse])
async def get_transaction_sources(txn_id: str, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(TransactionSource, ParsedTransaction)
        .join(ParsedTransaction, TransactionSource.parsed_txn_id == ParsedTransaction.id)
        .join(
            CanonicalTransaction,
            TransactionSource.canonical_txn_id == CanonicalTransaction.id,
        )
        .where(
            TransactionSource.canonical_txn_id == txn_id,
            CanonicalTransaction.user_id == user.id,
        )
    )
    rows = result.all()

    return [
        TransactionSourceResponse(
            parsed_txn_id=str(parsed.id),
            statement_id=str(parsed.statement_id) if parsed.statement_id else None,
            source_type=parsed.source_type,
            description_raw=parsed.description_raw,
            confidence=parsed.confidence,
            extraction_method=parsed.extraction_method,
            match_method=source.match_method,
            is_primary=source.is_primary,
        )
        for source, parsed in rows
    ]
