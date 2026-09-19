"""Alembic environment for TradeValue's PostgreSQL schema."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The project currently owns its schema as reviewed SQL migrations rather than
# SQLAlchemy ORM metadata. Schema drift is checked from PostgreSQL's catalogs.
target_metadata = None


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL or TEST_DATABASE_URL is required for migrations")
    if not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise RuntimeError("TradeValue migrations require PostgreSQL")
    return url


def configure(connection=None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        literal_binds=url is not None,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    configure(url=database_url())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = config.get_section(config.config_ini_section, {})
    settings["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        settings,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-c lock_timeout=10000 -c statement_timeout=120000"},
    )

    with connectable.connect() as connection:
        configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
