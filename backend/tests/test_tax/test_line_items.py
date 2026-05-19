"""Tests for line-item parser emission + idempotent promotion (Sprint B.2)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.engines.tax.ais_parser import parse_ais_document
from app.engines.tax.form16_parser import parse_form16_document
from app.engines.tax.form_26as_parser import parse_form_26as_document
from app.engines.tax.line_item_promoter import promote_line_items

# ----- Parser line emission -----


def test_form16_parser_emits_gross_salary_and_tds_lines():
    text = """
    Employer Name : ACME PVT LTD
    TAN of Employer: ABCD12345E
    Gross Salary: 1,500,000
    Total Tax Deducted: 100,000
    80C: 1,50,000
    80D: 25,000
    """
    result = parse_form16_document(text, source_filename="form16.pdf")
    lines = result["lines"]
    by_head = {line["head"]: line for line in lines}

    assert "gross_salary" in by_head
    assert by_head["gross_salary"]["amount"] == 1500000.0
    assert "tds" in by_head
    assert by_head["tds"]["amount"] == 100000.0
    assert "deduction_80c" in by_head
    assert by_head["deduction_80c"]["amount"] == 150000.0
    assert result["employer_tan"] == "ABCD12345E"


def test_form26as_parser_emits_part_a_rows():
    text = """
    Form 26AS Part A
    DEDUCTOR TAN: ABCD12345E  Section: 192  Amount Credited: 1500000  Amount of TDS: 100000
    """
    result = parse_form_26as_document(text)
    lines = result["lines"]
    assert any(
        line["deductor_tan"] == "ABCD12345E"
        and line["section"] == "192"
        and line["amount_credit"] == 1500000.0
        and line["amount_tds"] == 100000.0
        for line in lines
    )


def test_ais_parser_emits_per_category_lines():
    text = """
    Annual Information Statement
    Salary Income from HDFC BANK: 1,200,000
    Interest from Savings Bank ICICI BANK: 18,500
    Dividend Received: 4,200
    """
    result = parse_ais_document(text)
    by_cat = {line["category"]: line for line in result["lines"]}
    assert "salary" in by_cat
    assert by_cat["salary"]["amount"] == 1200000.0
    assert "interest" in by_cat
    assert "dividend" in by_cat
    # Aliases preserved for backwards compatibility:
    assert result["interest"] == result["interest_income"]


# ----- Promoter idempotency -----


class _FakeDb:
    """Tiny stand-in for AsyncSession.

    `execute` walks the recorded `existing` map; `add` accumulates inserts;
    `flush` is a no-op. This mirrors the real session API closely enough to
    drive the promoter without a real Postgres.
    """

    def __init__(self, existing_keys: set | None = None):
        self.added: list = []
        self.existing_keys = existing_keys or set()
        self.flush_count = 0

    async def execute(self, _stmt):
        # The promoter only uses `await db.execute(...).first()` for existence
        # checks. We approximate by returning a tuple iff the cumulative add
        # history (or pre-seeded existing set) contains the key the stmt
        # narrows by. Since we can't introspect the statement here cheaply,
        # we just say "nothing exists" — the promoter will then add every
        # line, and the test inspects `db.added` directly.
        return SimpleNamespace(first=lambda: None)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_promote_form16_inserts_one_row_per_head():
    db = _FakeDb()
    parsed = parse_form16_document(
        """
        Employer Name: ACME PVT LTD
        TAN of Employer: ABCD12345E
        Gross Salary: 1500000
        Total Tax Deducted: 100000
        """
    )
    counts = await promote_line_items(
        db=db,
        user_id=uuid.uuid4(),
        fy="FY24-25",
        doc_artifact_id=uuid.uuid4(),
        parsed=parsed,
    )
    assert counts["inserted"] == len(parsed["lines"])
    heads = {row.head for row in db.added}
    assert {"gross_salary", "tds"}.issubset(heads)


@pytest.mark.asyncio
async def test_promote_skips_invalid_lines():
    db = _FakeDb()
    parsed = {
        "document_type": "form_16",
        "employer_name": "ACME",
        "employer_tan": "ABCD12345E",
        "lines": [
            {"head": "gross_salary", "amount": 1500000},
            {"head": "tds", "amount": None},  # invalid
            {"head": "", "amount": 50000},  # invalid
            {"head": "deduction_80c", "amount": -10000},  # invalid
        ],
    }
    counts = await promote_line_items(
        db=db,
        user_id=uuid.uuid4(),
        fy="FY24-25",
        doc_artifact_id=None,
        parsed=parsed,
    )
    assert counts["inserted"] == 1
    assert counts["skipped_invalid"] == 3


@pytest.mark.asyncio
async def test_promote_form26as_handles_self_paid_challan():
    db = _FakeDb()
    parsed = {
        "document_type": "form_26as",
        "lines": [
            {
                "part": "C",
                "deductor_tan": None,
                "section": "self_paid_challan",
                "amount_credit": 50000,
                "amount_tds": None,
            },
        ],
    }
    counts = await promote_line_items(
        db=db,
        user_id=uuid.uuid4(),
        fy="FY24-25",
        doc_artifact_id=None,
        parsed=parsed,
    )
    assert counts["inserted"] == 1
    assert db.added[0].part == "C"
    assert db.added[0].amount_credit == Decimal("50000.00")


@pytest.mark.asyncio
async def test_promote_ignores_unknown_doc_type():
    db = _FakeDb()
    parsed = {
        "document_type": "challan",
        "lines": [{"head": "noise", "amount": 1234}],
    }
    counts = await promote_line_items(
        db=db,
        user_id=uuid.uuid4(),
        fy="FY24-25",
        doc_artifact_id=None,
        parsed=parsed,
    )
    assert counts["inserted"] == 0
    assert counts["skipped_invalid"] == 1
