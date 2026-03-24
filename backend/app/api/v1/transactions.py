from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession
from app.engines.ledger.account_labels import bank_account_label
from app.engines.ledger.category_enrichment import infer_uncategorized_category
from app.engines.ledger.transfer_reclassifier import reclassify_transfer_payments_for_user
from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.models.parsed_transaction import ParsedTransaction
from app.models.transaction_source import TransactionSource
from app.models.user_override import UserOverride
from app.schemas.transaction import (
    AutoCategorizeResponse,
    ReclassifyTransferResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionSourceResponse,
    TransactionUpdateRequest,
)

router = APIRouter()

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
        category_name=category_name,
        bank_name=t.bank_name,
        bank_label=bank_account_label(t.bank_name, t.account_type),
        account_type=t.account_type,
        account_masked=t.account_masked,
        is_recurring=t.is_recurring,
        is_anomalous=t.is_anomalous,
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

    # Record overrides and apply changes
    updates = request.model_dump(exclude_unset=True)
    for field, new_value in updates.items():
        old_value = str(getattr(txn, field, None))
        override = UserOverride(
            user_id=user.id,
            canonical_txn_id=txn.id,
            field_name=field,
            old_value=old_value,
            new_value=str(new_value) if new_value is not None else "",
        )
        db.add(override)
        setattr(txn, field, new_value)

    if "category_id" in updates:
        txn.category_source = "user"

    await db.flush()

    # Re-fetch with category name
    result = await db.execute(
        select(CanonicalTransaction, Category.name.label("category_name"))
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(CanonicalTransaction.id == txn_id)
    )
    row = result.one()
    return _txn_to_response(row[0], category_name=row[1])


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
            source_type=parsed.source_type,
            description_raw=parsed.description_raw,
            confidence=parsed.confidence,
            extraction_method=parsed.extraction_method,
            match_method=source.match_method,
            is_primary=source.is_primary,
        )
        for source, parsed in rows
    ]
