"""Alembic environment — async-compatible with SQLAlchemy 2.x.

Uses the DATABASE_URL from the application Settings so credentials
are never stored in alembic.ini.

Run migrations::

    alembic upgrade head
    alembic downgrade -1
    alembic revision --autogenerate -m "describe change"
"""

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Alembic Config object ──────────────────────────────────────────────────────
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ── Import all ORM models so Alembic can detect schema changes ─────────────────
# This must happen before target_metadata is read.
from src.domain.models.base import Base  # noqa: E402
import src.domain.models  # noqa: F401, E402 — registers all mappers via __init__

target_metadata = Base.metadata

# ── Inject DATABASE_URL from application settings ─────────────────────────────
# This overrides any sqlalchemy.url in alembic.ini.
try:
    from src.infra.config import get_settings  # noqa: E402

    _settings = get_settings()
    config.set_main_option("sqlalchemy.url", _settings.database_url)
    logger.info("Alembic using DATABASE_URL from application settings.")
except Exception as exc:  # settings may fail in CI without full env
    logger.warning(
        "Could not load application settings for Alembic; "
        "falling back to alembic.ini sqlalchemy.url. Error: %s",
        exc,
    )


# ── Offline mode (generates SQL without a live DB connection) ─────────────────

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout without opening a real connection.
    Useful for generating migration scripts for manual review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (async) ───────────────────────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against a live async database connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (live DB) migration runs."""
    asyncio.run(run_async_migrations())


# ── Dispatch ──────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
