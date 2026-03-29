import uuid
from types import SimpleNamespace

import pytest

from app.engines.parser.password_patterns import (
    PdfPasswordResolution,
    resolve_pdf_password,
)


class _DummyScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DummyExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _DummyScalarResult(self._rows)


class _DummyDb:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _DummyExecResult(self._rows)


@pytest.mark.asyncio
async def test_resolve_pdf_password_not_encrypted(monkeypatch):
    async_db = _DummyDb(rows=[])
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_without_password",
        lambda _content: True,
    )
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_with_password",
        lambda _content, _password: False,
    )

    result = await resolve_pdf_password(
        db=async_db,
        user_id=uuid.uuid4(),
        pdf_content=b"pdf",
        source_filename="statement.pdf",
    )
    assert isinstance(result, PdfPasswordResolution)
    assert result.encrypted is False
    assert result.password is None
    assert result.source == "not_encrypted"


@pytest.mark.asyncio
async def test_resolve_pdf_password_prefers_valid_manual_password(monkeypatch):
    async_db = _DummyDb(rows=[])
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_without_password",
        lambda _content: False,
    )
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_with_password",
        lambda _content, password: password == "RIGHT123",
    )

    result = await resolve_pdf_password(
        db=async_db,
        user_id=uuid.uuid4(),
        pdf_content=b"pdf",
        manual_password="RIGHT123",
        source_filename="hdfc-cc.pdf",
    )
    assert result.encrypted is True
    assert result.password == "RIGHT123"
    assert result.source == "manual"
    assert result.manual_password_rejected is False


@pytest.mark.asyncio
async def test_resolve_pdf_password_uses_pattern_when_manual_missing(monkeypatch):
    pattern_id = uuid.uuid4()
    row = SimpleNamespace(
        id=pattern_id,
        pattern_type="template",
        pattern_template="{customer_id}{dob_ddmmyyyy}",
        variables_json={"customer_id": "ANKI", "dob_ddmmyyyy": "17022002"},
        account_scope="credit_card",
        bank_code="HDFC",
        updated_at=None,
    )
    async_db = _DummyDb(rows=[row])
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_without_password",
        lambda _content: False,
    )
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_with_password",
        lambda _content, password: password == "ANKI17022002",
    )

    result = await resolve_pdf_password(
        db=async_db,
        user_id=uuid.uuid4(),
        pdf_content=b"pdf",
        bank_hint="HDFC",
        account_type_hint="credit_card",
        source_filename="hdfc-cc.pdf",
    )
    assert result.encrypted is True
    assert result.password == "ANKI17022002"
    assert result.source.startswith("pattern:")


@pytest.mark.asyncio
async def test_resolve_pdf_password_reports_unresolved(monkeypatch):
    async_db = _DummyDb(rows=[])
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_without_password",
        lambda _content: False,
    )
    monkeypatch.setattr(
        "app.engines.parser.password_patterns._can_open_with_password",
        lambda _content, _password: False,
    )

    result = await resolve_pdf_password(
        db=async_db,
        user_id=uuid.uuid4(),
        pdf_content=b"pdf",
        manual_password="WRONG123",
    )
    assert result.encrypted is True
    assert result.password is None
    assert result.source == "unresolved"
    assert result.manual_password_rejected is True
