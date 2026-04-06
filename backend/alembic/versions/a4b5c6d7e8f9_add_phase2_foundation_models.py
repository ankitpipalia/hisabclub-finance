"""add phase2 foundation models

Revision ID: a4b5c6d7e8f9
Revises: f9a0b1c2d3e4
Create Date: 2026-04-06 18:30:00.000000
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INSTITUTIONS = [
    ("HDFC Bank", "HDFC", "bank", "hdfc"),
    ("ICICI Bank", "ICICI", "bank", "icici"),
    ("State Bank of India", "SBI", "bank", "sbi"),
    ("Axis Bank", "AXIS", "bank", "axis"),
    ("Kotak Mahindra Bank", "KOTAK", "bank", "kotak"),
    ("Bank of Baroda", "BOB", "bank", "bob"),
    ("Punjab National Bank", "PNB", "bank", "pnb"),
    ("Canara Bank", "CANARA", "bank", "canara"),
    ("Union Bank of India", "UNION", "bank", "union"),
    ("IndusInd Bank", "INDUSIND", "bank", "indusind"),
    ("YES Bank", "YES", "bank", "yes"),
    ("Federal Bank", "FEDERAL", "bank", "federal"),
    ("IDBI Bank", "IDBI", "bank", "idbi"),
    ("Indian Overseas Bank", "IOB", "bank", "iob"),
    ("Bank of India", "BOI", "bank", "boi"),
    ("Indian Bank", "INDIAN_BANK", "bank", "indian-bank"),
]


def _enable_user_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_isolation ON {table_name}
        USING (app.is_worker_context() OR user_id = app.request_user_id())
        WITH CHECK (app.is_worker_context() OR user_id = app.request_user_id())
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO hisabclub_rls")


def _drop_user_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("short_name", sa.String(length=20), nullable=False),
        sa.Column("logo_key", sa.String(length=50), nullable=True),
        sa.Column("institution_type", sa.String(length=30), nullable=False, server_default="bank"),
        sa.Column(
            "supported_formats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("""'{"pdf": true, "xlsx": true, "xls": true, "csv": true}'::jsonb"""),
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_institutions_name"),
        sa.UniqueConstraint("short_name", name="uq_institutions_short_name"),
    )
    op.execute("GRANT SELECT ON institutions TO hisabclub_rls")

    institutions_table = sa.table(
        "institutions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=100)),
        sa.column("short_name", sa.String(length=20)),
        sa.column("logo_key", sa.String(length=50)),
        sa.column("institution_type", sa.String(length=30)),
        sa.column("supported_formats", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("is_system", sa.Boolean()),
    )
    institution_rows = [
        {
            "id": uuid.uuid4(),
            "name": name,
            "short_name": short_name,
            "logo_key": logo_key,
            "institution_type": institution_type,
            "supported_formats": {"pdf": True, "xlsx": True, "xls": True, "csv": True},
            "is_system": True,
        }
        for name, short_name, institution_type, logo_key in INSTITUTIONS
    ]
    op.bulk_insert(institutions_table, institution_rows)

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("institution_name", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("account_number_masked", sa.String(length=50), nullable=True),
        sa.Column("nickname", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_statement_date", sa.Date(), nullable=True),
        sa.Column("opening_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "institution_name",
            "account_type",
            "account_number_masked",
            name="uq_accounts_user_institution_type_masked",
        ),
        sa.CheckConstraint("status IN ('active','closed')", name="ck_accounts_status"),
    )
    op.create_index("ix_accounts_user_institution", "accounts", ["user_id", "institution_name"], unique=False)
    _enable_user_rls("accounts")

    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("pan_number_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column("statements", sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_statements_account_id", "statements", "accounts", ["account_id"], ["id"])
    op.create_index("ix_statements_account_id", "statements", ["account_id"], unique=False)

    op.create_table(
        "transaction_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parsed_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canonical_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("annotation_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("llm_response", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["canonical_transaction_id"], ["canonical_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parsed_transaction_id"], ["parsed_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_id"], ["statements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "annotation_type IN ('comment','correction_request','verification','flag')",
            name="ck_transaction_annotations_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','applied','rejected','acknowledged')",
            name="ck_transaction_annotations_status",
        ),
    )
    op.create_index(
        "ix_transaction_annotations_statement_created",
        "transaction_annotations",
        ["statement_id", "created_at"],
        unique=False,
    )
    _enable_user_rls("transaction_annotations")

    op.create_table(
        "conversation_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["statement_id"], ["statements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_conversation_threads_status"),
    )
    op.create_index(
        "ix_conversation_threads_user_updated",
        "conversation_threads",
        ["user_id", "updated_at"],
        unique=False,
    )
    _enable_user_rls("conversation_threads")

    op.create_table(
        "conversation_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("role IN ('system','user','assistant','tool')", name="ck_conversation_messages_role"),
    )
    op.create_index(
        "ix_conversation_messages_thread_index",
        "conversation_messages",
        ["thread_id", "message_index"],
        unique=False,
    )
    _enable_user_rls("conversation_messages")

    op.create_table(
        "tax_portal_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("assessment_year", sa.String(length=16), nullable=True),
        sa.Column("financial_year", sa.String(length=16), nullable=True),
        sa.Column("source_name", sa.String(length=100), nullable=True),
        sa.Column("pan_masked", sa.String(length=20), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column(
            "extracted_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("verification_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="parsed"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["document_artifact_id"], ["document_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('parsed','verified','needs_review')", name="ck_tax_portal_data_status"),
    )
    op.create_index(
        "ix_tax_portal_data_user_document_type",
        "tax_portal_data",
        ["user_id", "document_type"],
        unique=False,
    )
    _enable_user_rls("tax_portal_data")

    bind = op.get_bind()
    institutions_by_short = {
        row.short_name: row.id
        for row in bind.execute(sa.text("SELECT id, short_name FROM institutions"))
    }

    statements = bind.execute(
        sa.text(
            """
            SELECT id, user_id, bank_name, account_type, account_number_masked,
                   statement_period_start, statement_period_end
            FROM statements
            WHERE is_active = true
            ORDER BY user_id, bank_name, account_type, account_number_masked, created_at
            """
        )
    ).fetchall()

    account_rows: list[dict] = []
    account_key_to_id: dict[tuple[str, str, str, str | None], uuid.UUID] = {}
    account_id_to_key: dict[uuid.UUID, tuple[str, str, str, str | None]] = {}
    account_dates: dict[tuple[str, str, str, str | None], dict[str, object | None]] = defaultdict(
        lambda: {"opening_date": None, "last_statement_date": None}
    )

    short_to_name = {short: name for name, short, _itype, _logo in INSTITUTIONS}

    for row in statements:
        user_id = str(row.user_id)
        bank_name = (row.bank_name or "").strip().upper()
        account_type = (row.account_type or "").strip().lower() or "savings"
        account_number_masked = row.account_number_masked
        key = (user_id, bank_name, account_type, account_number_masked)

        if key not in account_key_to_id:
            account_id = uuid.uuid4()
            account_key_to_id[key] = account_id
            account_id_to_key[account_id] = key
            account_rows.append(
                {
                    "id": account_id,
                    "user_id": row.user_id,
                    "institution_id": institutions_by_short.get(bank_name),
                    "institution_name": short_to_name.get(bank_name, bank_name or "Unknown"),
                    "account_type": account_type,
                    "account_number_masked": account_number_masked,
                    "nickname": None,
                    "status": "active",
                    "metadata_json": None,
                    "last_statement_date": row.statement_period_end,
                    "opening_date": row.statement_period_start,
                }
            )

        dates = account_dates[key]
        if row.statement_period_start and (
            dates["opening_date"] is None or row.statement_period_start < dates["opening_date"]
        ):
            dates["opening_date"] = row.statement_period_start
        if row.statement_period_end and (
            dates["last_statement_date"] is None or row.statement_period_end > dates["last_statement_date"]
        ):
            dates["last_statement_date"] = row.statement_period_end

    accounts_table = sa.table(
        "accounts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("institution_id", postgresql.UUID(as_uuid=True)),
        sa.column("institution_name", sa.String(length=100)),
        sa.column("account_type", sa.String(length=50)),
        sa.column("account_number_masked", sa.String(length=50)),
        sa.column("nickname", sa.String(length=100)),
        sa.column("status", sa.String(length=20)),
        sa.column("metadata_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("last_statement_date", sa.Date()),
        sa.column("opening_date", sa.Date()),
    )
    for row in account_rows:
        key = account_id_to_key[row["id"]]
        row["opening_date"] = account_dates[key]["opening_date"]
        row["last_statement_date"] = account_dates[key]["last_statement_date"]

    if account_rows:
        op.bulk_insert(accounts_table, account_rows)

    for row in statements:
        key = (
            str(row.user_id),
            (row.bank_name or "").strip().upper(),
            (row.account_type or "").strip().lower() or "savings",
            row.account_number_masked,
        )
        account_id = account_key_to_id.get(key)
        if account_id is None:
            continue
        bind.execute(
            sa.text("UPDATE statements SET account_id = :account_id WHERE id = :statement_id"),
            {"account_id": account_id, "statement_id": row.id},
        )


def downgrade() -> None:
    _drop_user_rls("tax_portal_data")
    op.drop_index("ix_tax_portal_data_user_document_type", table_name="tax_portal_data")
    op.drop_table("tax_portal_data")

    _drop_user_rls("conversation_messages")
    op.drop_index("ix_conversation_messages_thread_index", table_name="conversation_messages")
    op.drop_table("conversation_messages")

    _drop_user_rls("conversation_threads")
    op.drop_index("ix_conversation_threads_user_updated", table_name="conversation_threads")
    op.drop_table("conversation_threads")

    _drop_user_rls("transaction_annotations")
    op.drop_index("ix_transaction_annotations_statement_created", table_name="transaction_annotations")
    op.drop_table("transaction_annotations")

    op.drop_index("ix_statements_account_id", table_name="statements")
    op.drop_constraint("fk_statements_account_id", "statements", type_="foreignkey")
    op.drop_column("statements", "account_id")

    op.drop_column("users", "onboarding_step")
    op.drop_column("users", "onboarding_completed")
    op.drop_column("users", "pan_number_encrypted")
    op.drop_column("users", "last_name")

    _drop_user_rls("accounts")
    op.drop_index("ix_accounts_user_institution", table_name="accounts")
    op.drop_table("accounts")

    op.execute("DROP TABLE IF EXISTS institutions")
