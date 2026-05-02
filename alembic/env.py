from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

import cmart.db.models  # noqa: F401 — ensure all models are registered on Base.metadata
from cmart.config import get_settings

# Import Base so Alembic can introspect all mapped models
from cmart.db.engine import Base  # noqa: F401

# Alembic Config object — provides access to the values in alembic.ini
config = context.config

# Set up Python logging using the ini file's [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object used for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve DATABASE_URL from application settings at migration time."""
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live connection)."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = create_async_engine(get_database_url(), future=True)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
