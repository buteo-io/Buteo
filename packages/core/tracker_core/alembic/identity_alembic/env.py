"""Alembic env for Identity DB. Uses same dynamic driver conversion as tenant migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from tracker_core.internal.appctx.config import AppConfig

# Ensure identity models are registered
from tracker_core.store.identity_db import GPSDevice, IdentityBase, Tenant  # noqa: F401

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", False):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = IdentityBase.metadata

current_url = config.get_main_option("sqlalchemy.url")
if not current_url or "driver://user" in current_url:
    config.set_main_option("sqlalchemy.url", AppConfig.identity_database_url)


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


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run_migrations_online_async())
    finally:
        loop.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
