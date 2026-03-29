import io
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.v1 import upload as upload_api
from app.engines.parser.base import StatementDuplicateError
from app.engines.parser.password_patterns import PdfPasswordResolution


class _DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DummyDb:
    def __init__(self, existing_pdf):
        self._existing_pdf = existing_pdf
        self.added = []
        self.executed = []

    async def execute(self, stmt, *_args, **_kwargs):
        self.executed.append(stmt)
        return _DummyResult(self._existing_pdf)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def _make_pdf_upload(filename: str = "statement.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(b"%PDF-1.4\nmock\n%%EOF"))


@pytest.mark.asyncio
async def test_duplicate_upload_without_force_reprocess_returns_409(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api.settings, "upload_dir", str(tmp_path))
    async def _fake_resolve_password(**_kwargs):
        return PdfPasswordResolution(
            password=None,
            encrypted=False,
            source="not_encrypted",
            attempted=0,
        )
    monkeypatch.setattr(upload_api, "resolve_pdf_password", _fake_resolve_password)

    db = _DummyDb(existing_pdf=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        await upload_api.upload_pdf(
            user=user,
            db=db,
            file=_make_pdf_upload("dup.pdf"),
            force_reprocess=False,
        )

    assert exc.value.status_code == 409
    assert "Enable reprocess" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_duplicate_upload_with_force_reprocess_enqueues_job(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api.settings, "upload_dir", str(tmp_path))
    seen: dict = {}

    async def _fake_enqueue_parse_job(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    async def _fake_ingest_pdf_knowledge(**_kwargs):
        return 1

    async def _fake_resolve_password(**_kwargs):
        return PdfPasswordResolution(
            password="ABCD1234",
            encrypted=True,
            source="manual",
            attempted=1,
        )

    monkeypatch.setattr(upload_api, "enqueue_parse_job", _fake_enqueue_parse_job)
    monkeypatch.setattr(upload_api, "ingest_pdf_knowledge", _fake_ingest_pdf_knowledge)
    monkeypatch.setattr(upload_api, "resolve_pdf_password", _fake_resolve_password)

    db = _DummyDb(existing_pdf=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4())

    response = await upload_api.upload_pdf(
        user=user,
        db=db,
        file=_make_pdf_upload("dup-force.pdf"),
        password="ABCD1234",
        bank_hint="HDFC Bank",
        account_type_hint="credit_card",
        force_reprocess=True,
    )

    raw_pdf = next(obj for obj in db.added if obj.__class__.__name__ == "RawPdf")
    assert raw_pdf.source_type == "manual_reprocess"
    assert Path(raw_pdf.storage_path).exists()
    assert response.status == "reviewing"
    assert "under review" in response.message.lower()
    assert seen["priority"] == 120
    assert seen["raw_pdf_id"] == raw_pdf.id
    assert seen["payload"]["bank_hint"] == "HDFC"
    assert seen["payload"]["account_type_hint"] == "credit_card"
    assert seen["payload"]["allow_semantic_duplicate"] is True
    assert seen["payload"]["password_enc"]


@pytest.mark.asyncio
async def test_new_upload_creates_manual_upload_record_and_reviewing_status(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api.settings, "upload_dir", str(tmp_path))
    seen: dict = {}

    async def _fake_enqueue_parse_job(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    async def _fake_ingest_pdf_knowledge(**_kwargs):
        return 1

    async def _fake_resolve_password(**_kwargs):
        return PdfPasswordResolution(
            password=None,
            encrypted=False,
            source="not_encrypted",
            attempted=0,
        )

    monkeypatch.setattr(upload_api, "enqueue_parse_job", _fake_enqueue_parse_job)
    monkeypatch.setattr(upload_api, "ingest_pdf_knowledge", _fake_ingest_pdf_knowledge)
    monkeypatch.setattr(upload_api, "resolve_pdf_password", _fake_resolve_password)

    db = _DummyDb(existing_pdf=None)
    user = SimpleNamespace(id=uuid.uuid4())

    response = await upload_api.upload_pdf(
        user=user,
        db=db,
        file=_make_pdf_upload("new.pdf"),
    )

    raw_pdf = next(obj for obj in db.added if obj.__class__.__name__ == "RawPdf")
    assert raw_pdf.source_type == "manual_upload"
    assert response.status == "reviewing"
    assert seen["priority"] == 100
    assert seen["payload"]["allow_semantic_duplicate"] is False


@pytest.mark.asyncio
async def test_semantic_duplicate_job_enqueue_returns_duplicate_status(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api.settings, "upload_dir", str(tmp_path))

    async def _fake_enqueue_parse_job(**_kwargs):
        raise StatementDuplicateError("semantic duplicate")

    async def _fake_ingest_pdf_knowledge(**_kwargs):
        return 1

    async def _fake_resolve_password(**_kwargs):
        return PdfPasswordResolution(
            password=None,
            encrypted=False,
            source="not_encrypted",
            attempted=0,
        )

    monkeypatch.setattr(upload_api, "enqueue_parse_job", _fake_enqueue_parse_job)
    monkeypatch.setattr(upload_api, "ingest_pdf_knowledge", _fake_ingest_pdf_knowledge)
    monkeypatch.setattr(upload_api, "resolve_pdf_password", _fake_resolve_password)

    db = _DummyDb(existing_pdf=None)
    user = SimpleNamespace(id=uuid.uuid4())

    response = await upload_api.upload_pdf(
        user=user,
        db=db,
        file=_make_pdf_upload("semantic-dup.pdf"),
    )

    assert response.status == "duplicate"
    assert "semantic duplicate" in response.message
