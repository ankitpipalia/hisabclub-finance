from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_request_user_context(db: AsyncSession, *, user_id: uuid.UUID | str) -> None:
    user_value = str(user_id)
    await db.execute(text("SELECT set_config('app.worker_mode', '0', true)"))
    await db.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": user_value},
    )


async def set_worker_context(db: AsyncSession) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', '', true)"))
    await db.execute(text("SELECT set_config('app.worker_mode', '1', true)"))


async def apply_rls_db_role(db: AsyncSession, *, role_name: str | None) -> None:
    if not role_name:
        return
    safe_role = role_name.replace('"', "").strip()
    if not safe_role:
        return
    try:
        await db.execute(text(f'SET ROLE "{safe_role}"'))
    except Exception:
        # Best effort: some environments may not allow role switching.
        return
