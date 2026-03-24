import io
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.v1 import upload as upload_api


class _DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DummyDb:
    def __init__(self, existing_pdf):
        self._existing_pdf = existing_pdf
        self.added = []

    async def execute(self, *_args, **_kwargs):
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
    db = _DummyDb(existing_pdf=object())
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
async def test_duplicate_upload_with_force_reprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api.settings, "upload_dir", str(tmp_path))

    async def _fake_parse_statement(**_kwargs):
        return SimpleNamespace(transaction_count=5, bank_name="HDFC")

    async def _fake_reclassify(**_kwargs):
        return SimpleNamespace(
            scanned=0,
            updated=0,
            matched_credit_card_pairs=0,
            llm_checked=0,
            llm_promoted=0,
        )

    monkeypatch.setattr(upload_api, "parse_statement", _fake_parse_statement)
    monkeypatch.setattr(upload_api, "reclassify_transfer_payments_for_user", _fake_reclassify)

    db = _DummyDb(existing_pdf=object())
    user = SimpleNamespace(id=uuid.uuid4())

    response = await upload_api.upload_pdf(
        user=user,
        db=db,
        file=_make_pdf_upload("dup-force.pdf"),
        force_reprocess=True,
    )

    raw_pdf = next(obj for obj in db.added if obj.__class__.__name__ == "RawPdf")
    assert raw_pdf.source_type == "manual_reprocess"
    assert Path(raw_pdf.storage_path).exists()
    assert response.status == "success"
    assert response.message == "Reprocessed 5 transactions from HDFC"


@pytest.mark.asyncio
async def test_new_upload_creates_manual_upload_record(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api.settings, "upload_dir", str(tmp_path))

    async def _fake_parse_statement(**_kwargs):
        return SimpleNamespace(transaction_count=3, bank_name="AXIS")

    async def _fake_reclassify(**_kwargs):
        return SimpleNamespace(
            scanned=0,
            updated=0,
            matched_credit_card_pairs=0,
            llm_checked=0,
            llm_promoted=0,
        )

    monkeypatch.setattr(upload_api, "parse_statement", _fake_parse_statement)
    monkeypatch.setattr(upload_api, "reclassify_transfer_payments_for_user", _fake_reclassify)

    db = _DummyDb(existing_pdf=None)
    user = SimpleNamespace(id=uuid.uuid4())

    response = await upload_api.upload_pdf(
        user=user,
        db=db,
        file=_make_pdf_upload("new.pdf"),
    )

    raw_pdf = next(obj for obj in db.added if obj.__class__.__name__ == "RawPdf")
    assert raw_pdf.source_type == "manual_upload"
    assert response.status == "success"
    assert response.message == "Parsed 3 transactions from AXIS"
