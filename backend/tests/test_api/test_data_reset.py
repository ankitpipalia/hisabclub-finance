import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app.engines.account.data_reset import _delete_user_rows


class _Result:
    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount

    def all(self):
        return []


class _FakeDb:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


def _to_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_delete_user_rows_deletes_transaction_sources_before_parsed_transactions():
    db = _FakeDb()
    plan = await _delete_user_rows(db, user_id=uuid.uuid4())

    labels = list(plan.deleted_rows.keys())
    assert "transaction_sources" in labels
    assert "parsed_transactions" in labels
    assert labels.index("transaction_sources") < labels.index("parsed_transactions")


@pytest.mark.asyncio
async def test_delete_user_rows_transaction_source_delete_targets_parsed_and_canonical_refs():
    db = _FakeDb()
    await _delete_user_rows(db, user_id=uuid.uuid4())

    sql_statements = [_to_sql(stmt) for stmt in db.statements]
    ts_delete_sql = next(sql for sql in sql_statements if "DELETE FROM transaction_sources" in sql)

    assert "canonical_txn_id" in ts_delete_sql
    assert "parsed_txn_id" in ts_delete_sql

