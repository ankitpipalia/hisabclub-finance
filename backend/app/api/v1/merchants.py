from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.models.merchant import Merchant

router = APIRouter()


@router.get("")
async def list_merchants(
    user: CurrentUser,
    db: DbSession,
    search: str | None = Query(None),
):
    query = select(Merchant).order_by(Merchant.display_name)

    if search:
        query = query.where(
            Merchant.display_name.ilike(f"%{search}%")
            | Merchant.name_normalized.ilike(f"%{search}%")
        )

    result = await db.execute(query.limit(100))
    merchants = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "name": m.display_name,
            "name_normalized": m.name_normalized,
            "category_id": str(m.default_category_id) if m.default_category_id else None,
            "merchant_type": m.merchant_type,
        }
        for m in merchants
    ]
