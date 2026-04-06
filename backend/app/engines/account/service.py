from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.institution import Institution


async def ensure_account_record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    bank_name: str | None,
    account_type: str | None,
    account_number_masked: str | None,
    statement_period_end: date | None = None,
    statement_period_start: date | None = None,
    metadata_json: dict | None = None,
) -> Account | None:
    normalized_bank = (bank_name or "").strip().upper()
    normalized_type = (account_type or "").strip().lower()
    if not normalized_bank or not normalized_type:
        return None

    institution = (
        await db.execute(
            select(Institution).where(
                or_(
                    Institution.short_name == normalized_bank,
                    Institution.name.ilike(normalized_bank),
                )
            )
        )
    ).scalar_one_or_none()

    institution_name = institution.name if institution else normalized_bank

    query = select(Account).where(
        Account.user_id == user_id,
        Account.institution_name == institution_name,
        Account.account_type == normalized_type,
    )
    if account_number_masked:
        query = query.where(Account.account_number_masked == account_number_masked)
    else:
        query = query.where(Account.account_number_masked.is_(None))

    account = (await db.execute(query.limit(1))).scalar_one_or_none()
    if account is None:
        account = Account(
            user_id=user_id,
            institution_id=institution.id if institution else None,
            institution_name=institution_name,
            account_type=normalized_type,
            account_number_masked=account_number_masked,
            metadata_json=metadata_json,
            last_statement_date=statement_period_end,
            opening_date=statement_period_start,
        )
        db.add(account)
        await db.flush()
        return account

    if institution and account.institution_id is None:
        account.institution_id = institution.id
    if statement_period_end and (
        account.last_statement_date is None or statement_period_end > account.last_statement_date
    ):
        account.last_statement_date = statement_period_end
    if statement_period_start and (
        account.opening_date is None or statement_period_start < account.opening_date
    ):
        account.opening_date = statement_period_start
    if metadata_json and not account.metadata_json:
        account.metadata_json = metadata_json
    await db.flush()
    return account

