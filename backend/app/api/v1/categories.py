from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.models.category import Category

router = APIRouter()


@router.get("")
async def list_categories(user: CurrentUser, db: DbSession):
    """List all categories (system + user) as a flat list."""
    result = await db.execute(
        select(Category)
        .where((Category.user_id == user.id) | (Category.user_id.is_(None)))
        .order_by(Category.sort_order, Category.name)
    )
    categories = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "icon": c.icon,
            "color": c.color,
            "is_system": c.is_system,
        }
        for c in categories
    ]
