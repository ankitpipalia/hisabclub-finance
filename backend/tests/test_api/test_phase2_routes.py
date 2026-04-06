from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import accounts as accounts_api
from app.api.v1 import auth as auth_api
from app.api.v1 import conversations as conversations_api


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _QueuedDb:
    def __init__(self, responses):
        self.responses = list(responses)
        self.added = []
        self.flush_count = 0
        self.refresh_count = 0

    async def execute(self, *_args, **_kwargs):
        return self.responses.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def refresh(self, _obj):
        self.refresh_count += 1


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_tokens(monkeypatch):
    db = _QueuedDb([_ScalarOneOrNoneResult(None)])
    monkeypatch.setattr(auth_api, "create_tokens", lambda user_id: {"access_token": f"t-{user_id}", "refresh_token": "r"})

    response = await auth_api.register(
        auth_api.RegisterRequest(
            email="phase2@example.com",
            display_name="Phase 2",
            password="ValidPassword@123",
            first_name="Phase",
            last_name="Two",
        ),
        db,
    )

    assert response["access_token"].startswith("t-")
    assert len(db.added) == 1
    assert db.added[0].email == "phase2@example.com"
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email():
    existing = SimpleNamespace(id=uuid.uuid4(), email="phase2@example.com")
    db = _QueuedDb([_ScalarOneOrNoneResult(existing)])

    with pytest.raises(auth_api.HTTPException) as exc:
        await auth_api.register(
            auth_api.RegisterRequest(
                email="phase2@example.com",
                display_name="Phase 2",
                password="ValidPassword@123",
            ),
            db,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_get_accounts_tree_serializes_institution_uuid_and_latest_balance():
    institution_id = uuid.uuid4()
    account_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    account = SimpleNamespace(
        id=account_id,
        institution_name="HDFC Bank",
        institution_id=institution_id,
        account_type="savings",
        account_number_masked="XX1234",
        nickname="Primary",
        status="active",
        metadata_json=None,
        last_statement_date=None,
        opening_date=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    statement = SimpleNamespace(
        account_id=account_id,
        account_type="savings",
        closing_balance=4321.0,
        total_amount_due=None,
        bank_name="HDFC",
        transaction_count=12,
        statement_period_end=date(2026, 3, 31),
        created_at=datetime.now(timezone.utc),
    )
    coverage = SimpleNamespace(
        bank_name="HDFC",
        account_number_masked="XX1234",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )
    institution = SimpleNamespace(
        id=institution_id,
        name="HDFC Bank",
        short_name="HDFC",
        logo_key="hdfc",
        institution_type="bank",
        supported_formats={"pdf": True},
        is_system=True,
    )
    db = _QueuedDb(
        [
            _ScalarsResult([account]),
            _ScalarsResult([statement]),
            _ScalarsResult([coverage]),
            _ScalarsResult([institution]),
        ]
    )

    result = await accounts_api.get_accounts_tree(user, db)

    assert len(result) == 1
    assert result[0].institution is not None
    assert result[0].institution.id == str(institution_id)
    assert result[0].accounts[0].latest_balance == 4321.0
    assert result[0].accounts[0].period_coverage[0].start == date(2026, 3, 1)


@pytest.mark.asyncio
async def test_resolve_conversation_refreshes_thread_before_serializing():
    user = SimpleNamespace(id=uuid.uuid4())
    thread = SimpleNamespace(
        id=uuid.uuid4(),
        statement_id=None,
        title="Thread",
        status="active",
        summary=None,
        metadata_json={"pending_question_count": 1},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db = _QueuedDb([_ScalarOneOrNoneResult(thread)])

    response = await conversations_api.resolve_conversation(str(thread.id), user, db)

    assert response.resolved is True
    assert response.thread.status == "archived"
    assert response.thread.pending_question_count == 0
    assert db.flush_count == 1
    assert db.refresh_count == 1
