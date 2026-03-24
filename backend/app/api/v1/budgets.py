from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession
from app.models.budget import Budget
from app.models.canonical_transaction import CanonicalTransaction
from app.models.category import Category
from app.schemas.budget import (
    BudgetCreateRequest,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpdateRequest,
)

router = APIRouter()


def _current_period_range(period: str) -> tuple[date, date]:
    """Return (start, end) dates for the current period."""
    today = date.today()
    if period == "monthly":
        start = today.replace(day=1)
        # Last day of current month
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            end = today.replace(month=today.month + 1, day=1)
        return start, end
    else:  # yearly
        start = today.replace(month=1, day=1)
        end = today.replace(year=today.year + 1, month=1, day=1)
        return start, end


async def _compute_spent(
    db, user_id, category_id: str | None, period: str
) -> float:
    """Compute total debit spending for a budget's category in the current period."""
    period_start, period_end = _current_period_range(period)

    query = (
        select(func.coalesce(func.sum(CanonicalTransaction.amount), 0))
        .where(CanonicalTransaction.user_id == user_id)
        .where(CanonicalTransaction.transaction_nature == "expense")
        .where(CanonicalTransaction.is_excluded == False)  # noqa: E712
        .where(CanonicalTransaction.transaction_date >= period_start)
        .where(CanonicalTransaction.transaction_date < period_end)
    )

    if category_id is not None:
        query = query.where(CanonicalTransaction.category_id == category_id)

    result = await db.execute(query)
    return float(result.scalar() or 0)


def _budget_to_response(
    budget: Budget, category_name: str | None, spent_amount: float
) -> BudgetResponse:
    amount_limit = float(budget.amount_limit)
    remaining = max(amount_limit - spent_amount, 0)
    percentage_used = (spent_amount / amount_limit * 100) if amount_limit > 0 else 0

    return BudgetResponse(
        id=str(budget.id),
        category_id=str(budget.category_id) if budget.category_id else None,
        category_name=category_name,
        amount_limit=amount_limit,
        period=budget.period,
        is_active=budget.is_active,
        spent_amount=round(spent_amount, 2),
        remaining=round(remaining, 2),
        percentage_used=round(percentage_used, 2),
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


@router.get("", response_model=BudgetListResponse)
async def list_budgets(user: CurrentUser, db: DbSession):
    query = (
        select(Budget, Category.name.label("category_name"))
        .outerjoin(Category, Budget.category_id == Category.id)
        .where(Budget.user_id == user.id)
        .where(Budget.is_active == True)  # noqa: E712
        .order_by(Budget.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    for budget, category_name in rows:
        spent = await _compute_spent(
            db, user.id, budget.category_id, budget.period
        )
        items.append(_budget_to_response(budget, category_name, spent))

    return BudgetListResponse(items=items, total=len(items))


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    request: BudgetCreateRequest, user: CurrentUser, db: DbSession
):
    # Check for duplicate
    existing_query = select(Budget).where(
        Budget.user_id == user.id,
        Budget.period == request.period,
        Budget.is_active == True,  # noqa: E712
    )
    if request.category_id:
        existing_query = existing_query.where(
            Budget.category_id == request.category_id
        )
    else:
        existing_query = existing_query.where(Budget.category_id.is_(None))

    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A budget for this category and period already exists.",
        )

    budget = Budget(
        user_id=user.id,
        category_id=request.category_id,
        amount_limit=request.amount_limit,
        period=request.period,
    )
    db.add(budget)
    await db.flush()

    # Fetch category name
    category_name = None
    if budget.category_id:
        cat = (
            await db.execute(
                select(Category.name).where(Category.id == budget.category_id)
            )
        ).scalar_one_or_none()
        category_name = cat

    spent = await _compute_spent(db, user.id, budget.category_id, budget.period)
    return _budget_to_response(budget, category_name, spent)


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: str,
    request: BudgetUpdateRequest,
    user: CurrentUser,
    db: DbSession,
):
    result = await db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(budget, field, value)

    await db.flush()

    # Fetch category name
    category_name = None
    if budget.category_id:
        cat = (
            await db.execute(
                select(Category.name).where(Category.id == budget.category_id)
            )
        ).scalar_one_or_none()
        category_name = cat

    spent = await _compute_spent(db, user.id, budget.category_id, budget.period)
    return _budget_to_response(budget, category_name, spent)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: str, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    budget.is_active = False
    await db.flush()
