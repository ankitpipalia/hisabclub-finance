"""Tests for missing-document checklist (Sprint B.4) + CA export pack (Sprint B.5)."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.engines.tax.checklist import ChecklistItem, ChecklistResponse

# ----- Checklist primitive types -----


def test_checklist_item_has_required_fields():
    item = ChecklistItem(
        kind="MISSING_AIS",
        severity="block_filing",
        title="Upload AIS",
        detail="...",
        cta_link="/tax?upload=ais",
        evidence_count=0,
    )
    assert item.severity in {"block_filing", "warning", "info"}


def test_checklist_response_is_immutable_tuple():
    response = ChecklistResponse(
        fy="FY24-25",
        items=(
            ChecklistItem(
                kind="MISSING_AIS",
                severity="block_filing",
                title="Upload AIS",
                detail="",
            ),
        ),
    )
    assert isinstance(response.items, tuple)
    assert response.items[0].kind == "MISSING_AIS"


# ----- CA pack helpers (string-level) -----


def test_ca_pack_summary_includes_recommended_regime():
    """Smoke-test the summary builder via the regime comparator output."""
    from app.engines.tax.export.ca_pack import _build_summary_md
    from app.engines.tax.regime import TaxInputs, compare

    comparison = compare("FY24-25", TaxInputs(gross_salary=Decimal("1500000")))
    summary = _build_summary_md(
        "FY24-25",
        comparison,
        ChecklistResponse(fy="FY24-25", items=()),
        [],
    )
    assert "Recommended regime" in summary
    assert comparison.recommendation in summary


def test_ca_pack_ledger_csv_headers_match_schema():
    from app.engines.tax.export.ca_pack import _build_ledger_csv

    txns = [
        SimpleNamespace(
            id=uuid.uuid4(),
            transaction_date=date(2024, 5, 1),
            amount=Decimal("1000.00"),
            direction="debit",
            transaction_nature="expense",
            merchant_raw="SWIGGY",
            category_id=None,
            bank_name="HDFC",
            account_masked="XX1234",
            extraction_source="template",
            validation_status="valid",
            source_statement_id=None,
        )
    ]
    csv_text = _build_ledger_csv(txns)
    first_line = csv_text.splitlines()[0]
    assert "transaction_date" in first_line
    assert "amount" in first_line
    assert "validation_status" in first_line


def test_ca_pack_documents_csv_includes_artifact_metadata():
    from app.engines.tax.export.ca_pack import _build_documents_csv

    artifact = SimpleNamespace(
        id=uuid.uuid4(),
        file_name="form16.pdf",
        file_ext=".pdf",
        doc_type="form_16",
        file_hash_sha256="abc123" * 10 + "abcd",
        created_at=datetime.now(timezone.utc),
    )
    csv_text = _build_documents_csv([artifact])
    assert "form16.pdf" in csv_text
    assert "form_16" in csv_text


def test_ca_pack_zip_round_trip(monkeypatch):
    """Mock the DB-touching parts of build_ca_pack and assert the zip is
    well-formed with every expected file."""
    from app.engines.tax.export import ca_pack as ca_pack_mod

    async def _fake_ledger(_db, _user_id, _start, _end):
        return []

    async def _fake_docs(_db, _user_id):
        return []

    async def _fake_matches(_db, _user_id):
        return []

    async def _fake_reports(_db, _user_id, _fy):
        return []

    async def _fake_checklist(_db, _user_id, _fy):
        return ChecklistResponse(fy=_fy, items=())

    async def _fake_scalars(*_args, **_kwargs):
        # Mock query returning empty .scalars().all()
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [])
        )

    monkeypatch.setattr(ca_pack_mod, "_ledger_for_fy", _fake_ledger)
    monkeypatch.setattr(ca_pack_mod, "_document_index", _fake_docs)
    monkeypatch.setattr(ca_pack_mod, "_matches_for", _fake_matches)
    monkeypatch.setattr(ca_pack_mod, "run_all_reconciliations", _fake_reports)
    monkeypatch.setattr(ca_pack_mod, "build_checklist", _fake_checklist)

    class _Db:
        async def execute(self, *_a, **_k):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [])
            )

    import asyncio

    pack = asyncio.run(
        ca_pack_mod.build_ca_pack(_Db(), uuid.uuid4(), "FY24-25")
    )
    assert pack.filename == "hisabclub_capack_FY24-25.zip"

    with zipfile.ZipFile(io.BytesIO(pack.content)) as zf:
        names = set(zf.namelist())
    assert {
        "summary.md",
        "ledger_FY.csv",
        "regime_comparison.json",
        "deduction_breakup.csv",
        "reconciliation_FY.csv",
        "documents.csv",
        "assumptions.md",
    }.issubset(names)


def test_ca_pack_rejects_bad_fy():
    from app.engines.tax.export.ca_pack import build_ca_pack

    class _Db:
        async def execute(self, *_a, **_k):
            raise AssertionError("should not be called for bad FY")

    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(build_ca_pack(_Db(), uuid.uuid4(), "not-a-fy"))
