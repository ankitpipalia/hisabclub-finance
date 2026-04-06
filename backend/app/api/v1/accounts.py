from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.engines.account.service import ensure_account_record
from app.models.account import Account
from app.models.institution import Institution
from app.models.statement import Statement
from app.models.statement_period_coverage import StatementPeriodCoverage
from app.schemas.accounts import (
    AccountCreateRequest,
    AccountResponse,
    AccountStatementsSummary,
    AccountTreeItem,
    AccountUpdateRequest,
    InstitutionAccountGroup,
    InstitutionResponse,
)
from app.schemas.statement import StatementResponse

router = APIRouter()


def _to_account_response(account: Account) -> AccountResponse:
    return AccountResponse.model_validate(
        {
            "id": str(account.id),
            "institution_id": str(account.institution_id) if account.institution_id else None,
            "institution_name": account.institution_name,
            "account_type": account.account_type,
            "account_number_masked": account.account_number_masked,
            "nickname": account.nickname,
            "status": account.status,
            "metadata_json": account.metadata_json,
            "last_statement_date": account.last_statement_date,
            "opening_date": account.opening_date,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }
    )


def _to_institution_response(institution: Institution) -> InstitutionResponse:
    return InstitutionResponse.model_validate(
        {
            "id": str(institution.id),
            "name": institution.name,
            "short_name": institution.short_name,
            "logo_key": institution.logo_key,
            "institution_type": institution.institution_type,
            "supported_formats": institution.supported_formats,
            "is_system": institution.is_system,
        }
    )


def _to_statement_summary(statement: Statement) -> StatementResponse:
    return StatementResponse(
        id=str(statement.id),
        pdf_id=str(statement.pdf_id) if statement.pdf_id else None,
        pdf_filename=None,
        bank_name=statement.bank_name,
        account_type=statement.account_type,
        account_number_masked=statement.account_number_masked,
        statement_period_start=statement.statement_period_start,
        statement_period_end=statement.statement_period_end,
        due_date=statement.due_date,
        min_amount_due=float(statement.min_amount_due) if statement.min_amount_due else None,
        total_amount_due=float(statement.total_amount_due) if statement.total_amount_due else None,
        credit_limit=float(statement.credit_limit) if statement.credit_limit else None,
        opening_balance=float(statement.opening_balance) if statement.opening_balance else None,
        closing_balance=float(statement.closing_balance) if statement.closing_balance else None,
        parser_used=statement.parser_used,
        parse_status=statement.parse_status,
        transaction_count=statement.transaction_count,
        expected_row_count=statement.expected_row_count,
        extracted_row_count=statement.extracted_row_count,
        promoted_row_count=statement.promoted_row_count,
        quarantined_row_count=statement.quarantined_row_count,
        yield_rate=statement.yield_rate,
        created_at=statement.created_at,
    )


@router.get("", response_model=list[AccountResponse])
async def list_accounts(user: CurrentUser, db: DbSession):
    accounts = (
        await db.execute(
            select(Account)
            .where(Account.user_id == user.id)
            .order_by(Account.institution_name.asc(), Account.account_type.asc(), Account.created_at.asc())
        )
    ).scalars().all()
    return [_to_account_response(account) for account in accounts]


@router.get("/tree", response_model=list[InstitutionAccountGroup])
async def get_accounts_tree(user: CurrentUser, db: DbSession):
    accounts = (
        await db.execute(
            select(Account)
            .where(Account.user_id == user.id)
            .order_by(Account.institution_name.asc(), Account.account_type.asc(), Account.created_at.asc())
        )
    ).scalars().all()
    if not accounts:
        return []

    account_ids = [account.id for account in accounts]
    statements = (
        await db.execute(
            select(Statement)
            .where(Statement.user_id == user.id, Statement.account_id.in_(account_ids))
            .order_by(Statement.statement_period_end.desc(), Statement.created_at.desc())
        )
    ).scalars().all()
    coverage_rows = (
        await db.execute(
            select(StatementPeriodCoverage).where(
                StatementPeriodCoverage.user_id == user.id,
                StatementPeriodCoverage.account_number_masked.in_(
                    [account.account_number_masked for account in accounts if account.account_number_masked]
                ),
            )
        )
    ).scalars().all()
    institutions = (
        await db.execute(select(Institution).order_by(Institution.name.asc()))
    ).scalars().all()
    institution_by_id = {institution.id: institution for institution in institutions}

    statement_map: dict[str, list[Statement]] = defaultdict(list)
    for statement in statements:
        if statement.account_id:
            statement_map[str(statement.account_id)].append(statement)

    coverage_map: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    for coverage in coverage_rows:
        coverage_map[(coverage.bank_name, coverage.account_number_masked)].append(
            {"start": coverage.period_start, "end": coverage.period_end}
        )

    groups: dict[str, InstitutionAccountGroup] = {}
    for account in accounts:
        key = account.institution_name
        if key not in groups:
            institution = institution_by_id.get(account.institution_id) if account.institution_id else None
            groups[key] = InstitutionAccountGroup(
                institution=_to_institution_response(institution) if institution else None,
                institution_name=account.institution_name,
                accounts=[],
            )
        linked_statements = statement_map.get(str(account.id), [])
        latest_statement = linked_statements[0] if linked_statements else None
        latest_balance = None
        if latest_statement is not None:
            if latest_statement.account_type == "credit_card":
                latest_balance = float(latest_statement.total_amount_due or 0.0)
            else:
                latest_balance = (
                    float(latest_statement.closing_balance) if latest_statement.closing_balance else None
                )
        groups[key].accounts.append(
            AccountTreeItem(
                **_to_account_response(account).model_dump(),
                statement_count=len(linked_statements),
                total_transactions=sum(int(stmt.transaction_count or 0) for stmt in linked_statements),
                latest_balance=latest_balance,
                period_coverage=coverage_map.get(
                    ((latest_statement.bank_name if latest_statement else account.institution_name), account.account_number_masked),
                    [],
                ),
            )
        )

    return list(groups.values())


@router.get("/institutions", response_model=list[InstitutionResponse])
async def list_institutions(_user: CurrentUser, db: DbSession):
    institutions = (
        await db.execute(select(Institution).order_by(Institution.name.asc()))
    ).scalars().all()
    return [_to_institution_response(institution) for institution in institutions]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(request: AccountCreateRequest, user: CurrentUser, db: DbSession):
    account = await ensure_account_record(
        db,
        user_id=user.id,
        bank_name=request.institution_name,
        account_type=request.account_type,
        account_number_masked=request.account_number_masked,
        metadata_json=request.metadata_json,
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account payload.")
    if request.nickname:
        account.nickname = request.nickname
        await db.flush()
    return _to_account_response(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    request: AccountUpdateRequest,
    user: CurrentUser,
    db: DbSession,
):
    account = (
        await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user.id))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if request.nickname is not None:
        account.nickname = request.nickname.strip() or None
    if request.status is not None:
        normalized_status = request.status.strip().lower()
        if normalized_status not in {"active", "closed"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status.")
        account.status = normalized_status
    if request.metadata_json is not None:
        account.metadata_json = request.metadata_json
    await db.flush()
    return _to_account_response(account)


@router.delete("/{account_id}", response_model=AccountResponse)
async def close_account(account_id: str, user: CurrentUser, db: DbSession):
    account = (
        await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user.id))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    account.status = "closed"
    await db.flush()
    return _to_account_response(account)


@router.get("/{account_id}/statements", response_model=AccountStatementsSummary)
async def list_account_statements(account_id: str, user: CurrentUser, db: DbSession):
    account = (
        await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user.id))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    statements = (
        await db.execute(
            select(Statement)
            .where(Statement.user_id == user.id, Statement.account_id == account.id)
            .order_by(Statement.statement_period_end.desc(), Statement.created_at.desc())
        )
    ).scalars().all()
    return AccountStatementsSummary(
        account=_to_account_response(account),
        statements=[statement.model_dump() if hasattr(statement, "model_dump") else _to_statement_summary(statement).model_dump() for statement in statements],
    )
