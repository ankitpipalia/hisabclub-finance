from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models.base import Base

# Import all models so Alembic can detect them
from app.models import (  # noqa: F401
    account,
    bill,
    budget,
    canonical_transaction,
    category,
    connected_account,
    conversation,
    document_artifact,
    document_knowledge_chunk,
    extraction_job,
    institution,
    institution_parser_support,
    institution_password_pattern,
    insights,
    merchant,
    password_reset_token,
    parsed_transaction,
    raw_pdf,
    raw_sms,
    statement,
    statement_period_coverage,
    sync_cursor,
    tax_portal_data,
    transaction_annotation,
    transfer_match,
    transaction_source,
    user,
    user_override,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
