import csv
import io
from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category

router = APIRouter()


@router.get("/csv")
async def export_csv(
    user: CurrentUser,
    db: DbSession,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    bank: str | None = Query(None),
):
    query = (
        select(CanonicalTransaction, Category.name.label("category_name"))
        .outerjoin(Category, CanonicalTransaction.category_id == Category.id)
        .where(CanonicalTransaction.user_id == user.id)
        .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
    )

    if date_from:
        query = query.where(CanonicalTransaction.transaction_date >= date_from)
    if date_to:
        query = query.where(CanonicalTransaction.transaction_date <= date_to)
    if bank:
        query = query.where(CanonicalTransaction.bank_name == bank.upper())

    query = query.order_by(CanonicalTransaction.transaction_date.desc())

    result = await db.execute(query)
    rows = result.all()

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "date", "description", "merchant", "category",
            "amount", "direction", "nature", "bank", "account",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Data rows
        for txn, category_name in rows:
            writer.writerow([
                txn.transaction_date.isoformat(),
                txn.merchant_raw,
                txn.merchant_normalized or "",
                category_name or "",
                f"{float(txn.amount):.2f}",
                txn.direction,
                txn.transaction_nature,
                txn.bank_name or "",
                txn.account_masked or "",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )
