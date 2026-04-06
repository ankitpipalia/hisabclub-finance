from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1 import transactions as transactions_api
from app.models.canonical_transaction import CanonicalTransaction
from app.models.transaction_split import TransactionSplit
from app.schemas.transaction import TransactionSplitPartRequest


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


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def one(self):
        return self._rows[0]

    def one_or_none(self):
        return self._rows[0] if self._rows else None


class _DynamicDb:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self._calls = 0
        self.txn = None

    async def execute(self, *_args, **_kwargs):
        self._calls += 1
        if self._calls == 1:
            return _ScalarOneOrNoneResult(self.txn)
        if self._calls == 2:
            return _ScalarOneOrNoneResult(None)
        if self._calls == 3:
            children = [obj for obj in self.added if isinstance(obj, CanonicalTransaction)]
            return _RowsResult([(child, None) for child in children])
        if self._calls == 4:
            return _RowsResult([(self.txn, None)])
        raise AssertionError(f"Unexpected execute call {self._calls}")

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


class _QueuedDb:
    def __init__(self, responses):
        self.responses = list(responses)
        self.added = []
        self.flush_count = 0

    async def execute(self, *_args, **_kwargs):
        return self.responses.pop(0)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


def _txn():
    return SimpleNamespace(
        id=uuid.uuid4(),
        transaction_date=date(2026, 4, 1),
        posting_date=None,
        amount=1200.0,
        direction="debit",
        currency="INR",
        transaction_nature="expense",
        merchant_raw="AMAZON PAY",
        merchant_normalized="AMAZON PAY",
        category_id=None,
        category_source="auto",
        merchant_id=None,
        bank_name="HDFC",
        account_type="credit_card",
        account_masked="XX1234",
        is_recurring=False,
        is_anomalous=False,
        notes=None,
        tags=None,
        is_excluded=False,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_bulk_update_transactions_updates_each_selected_transaction():
    user = SimpleNamespace(id=uuid.uuid4())
    txn = _txn()
    db = _QueuedDb(
        [
            _ScalarsResult([txn]),
            _RowsResult([(txn, None)]),
        ]
    )

    response = await transactions_api.bulk_update_transactions(
        transactions_api.TransactionBulkUpdateRequest(
            transaction_ids=[str(txn.id)],
            notes="Reviewed manually",
            transaction_nature="tax",
        ),
        user=user,
        db=db,
    )

    assert response.updated_count == 1
    assert txn.notes == "Reviewed manually"
    assert txn.transaction_nature == "tax"
    assert len(db.added) == 2


@pytest.mark.asyncio
async def test_split_transaction_creates_children_and_lineage():
    user = SimpleNamespace(id=uuid.uuid4())
    txn = _txn()
    db = _DynamicDb()
    db.txn = txn

    response = await transactions_api.split_transaction(
            str(txn.id),
            transactions_api.TransactionSplitRequest(
                parts=[
                    TransactionSplitPartRequest(amount=700, merchant_raw="Amazon Shopping"),
                    TransactionSplitPartRequest(amount=500, merchant_raw="Amazon Wallet"),
                ],
                exclude_original=True,
            ),
        user=user,
        db=db,
    )

    created_children = [obj for obj in db.added if isinstance(obj, CanonicalTransaction)]
    split_links = [obj for obj in db.added if isinstance(obj, TransactionSplit)]

    assert len(response.created_transactions) == 2
    assert len(created_children) == 2
    assert len(split_links) == 2
    assert txn.is_excluded is True


@pytest.mark.asyncio
async def test_split_transaction_rejects_mismatched_amount_sum():
    user = SimpleNamespace(id=uuid.uuid4())
    txn = _txn()
    db = _QueuedDb([
        _ScalarOneOrNoneResult(txn),
        _ScalarOneOrNoneResult(None),
    ])

    with pytest.raises(transactions_api.HTTPException) as exc:
        await transactions_api.split_transaction(
            str(txn.id),
            transactions_api.TransactionSplitRequest(
                parts=[
                    TransactionSplitPartRequest(amount=600, merchant_raw="Part 1"),
                    TransactionSplitPartRequest(amount=500, merchant_raw="Part 2"),
                ]
            ),
            user=user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert "sum to the original amount" in exc.value.detail


@pytest.mark.asyncio
async def test_get_transaction_detail_includes_sources_overrides_and_split_children():
    user = SimpleNamespace(id=uuid.uuid4())
    txn = _txn()
    parent = _txn()
    child = _txn()
    child.id = uuid.uuid4()
    child.merchant_raw = "Split Child"
    source = SimpleNamespace(match_method="semantic", is_primary=True)
    parsed = SimpleNamespace(
        id=uuid.uuid4(),
        statement_id=uuid.uuid4(),
        source_type="statement",
        description_raw="RAW SOURCE TEXT",
        confidence=0.92,
        extraction_method="llm_vision_page_extract",
    )
    override = SimpleNamespace(
        id=uuid.uuid4(),
        field_name="notes",
        old_value=None,
        new_value="reviewed",
        override_reason=None,
        created_at=datetime.now(timezone.utc),
    )
    db = _QueuedDb(
        [
            _RowsResult([(txn, None)]),
            _RowsResult([(source, parsed)]),
            _ScalarsResult([override]),
            _RowsResult([(parent, None)]),
            _RowsResult([(child, None)]),
        ]
    )

    response = await transactions_api.get_transaction_detail(str(txn.id), user=user, db=db)

    assert response.transaction.id == str(txn.id)
    assert len(response.sources) == 1
    assert response.sources[0].parsed_txn_id == str(parsed.id)
    assert response.sources[0].statement_id == str(parsed.statement_id)
    assert len(response.overrides) == 1
    assert response.overrides[0].field_name == "notes"
    assert response.split_parent is not None
    assert response.split_parent.id == str(parent.id)
    assert len(response.split_children) == 1
    assert response.split_children[0].merchant_raw == "Split Child"
