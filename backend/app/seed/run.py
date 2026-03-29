"""Seed runner — populates categories, merchants, and patterns."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.category import Category
from app.models.merchant import Merchant, MerchantPattern
from app.security.tenant_context import apply_rls_db_role
from app.seed.categories import DEFAULT_CATEGORIES
from app.seed.merchants import MERCHANTS


async def seed_categories(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed default categories. Returns a mapping of 'Parent > Child' -> category_id."""
    # Check if already seeded
    result = await db.execute(select(Category).where(Category.is_system == True))  # noqa: E712
    if result.scalars().first():
        print("Categories already seeded, loading existing...")
        # Build mapping from existing
        result = await db.execute(select(Category))
        all_cats = result.scalars().all()
        mapping = {}
        parent_map = {str(c.id): c for c in all_cats}
        for c in all_cats:
            if c.parent_id:
                parent = parent_map.get(str(c.parent_id))
                if parent:
                    mapping[f"{parent.name} > {c.name}"] = c.id
            mapping[c.name] = c.id
        return mapping

    print("Seeding categories...")
    mapping: dict[str, uuid.UUID] = {}

    for sort_idx, (name, icon, color, subcategories) in enumerate(DEFAULT_CATEGORIES):
        parent = Category(
            name=name,
            icon=icon,
            color=color,
            is_system=True,
            sort_order=sort_idx,
        )
        db.add(parent)
        await db.flush()
        mapping[name] = parent.id

        for sub_idx, sub_name in enumerate(subcategories):
            child = Category(
                name=sub_name,
                parent_id=parent.id,
                icon=icon,
                color=color,
                is_system=True,
                sort_order=sub_idx,
            )
            db.add(child)
            await db.flush()
            mapping[f"{name} > {sub_name}"] = child.id

    await db.commit()
    print(f"  Created {len(mapping)} categories")
    return mapping


async def seed_merchants(db: AsyncSession, category_map: dict[str, uuid.UUID]) -> None:
    """Seed merchants and their matching patterns."""
    # Check if already seeded
    result = await db.execute(select(Merchant).limit(1))
    if result.scalars().first():
        print("Merchants already seeded, skipping.")
        return

    print("Seeding merchants...")
    count = 0

    for merchant_name, category_path, patterns in MERCHANTS:
        category_id = category_map.get(category_path)

        merchant = Merchant(
            name_normalized=merchant_name.upper().replace(" ", "_"),
            display_name=merchant_name,
            default_category_id=category_id,
        )
        db.add(merchant)
        await db.flush()

        for priority, (pattern, pattern_type) in enumerate(patterns):
            mp = MerchantPattern(
                merchant_id=merchant.id,
                pattern=pattern,
                pattern_type=pattern_type,
                priority=priority,
            )
            db.add(mp)

        count += 1

    await db.commit()
    print(f"  Created {count} merchants with patterns")


async def run_seed():
    print("=== HisabClub Seed Runner ===\n")
    async with async_session_factory() as db:
        if settings.db_set_role_on_connect:
            await apply_rls_db_role(db, role_name=settings.db_rls_role)
        category_map = await seed_categories(db)
        await seed_merchants(db, category_map)
    print("\nSeed complete!")


if __name__ == "__main__":
    asyncio.run(run_seed())
