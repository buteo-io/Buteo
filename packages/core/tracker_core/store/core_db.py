"""Async SQLAlchemy engine + session factory + Alembic bootstrap for Core DB.

Exposes:
    - :class:`CoreBase` — the declarative base for core models.
    - :data:`CoreSessionLocal` — dynamic session maker delegating to active tenant.
    - :func:`get_core_session` — FastAPI dependency yielding an ``AsyncSession``.
    - :func:`init_core_db` — runs Alembic migrations on a specific database (idempotent).
"""

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class CoreBase(DeclarativeBase):
    """Declarative base shared by every ORM model in core database."""


class DynamicSessionMaker:
    """Delegates session creation to active tenant_id context if set, else raises error."""

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        from tracker_core.store.tenant_db_manager import current_tenant_id, tenant_db_manager

        tid = current_tenant_id.get()
        if tid:
            maker = tenant_db_manager.get_tenant_sessionmaker(tid)
            return maker(*args, **kwargs)
        raise RuntimeError("No active tenant_id context set")


CoreSessionLocal = DynamicSessionMaker()


async def get_core_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a short-lived async session, closed on exit."""
    async with CoreSessionLocal() as session:
        yield session


async def init_core_db(database_url: str) -> None:
    """Run Alembic migrations to head. Idempotent.

    All schema changes flow through core_alembic/versions/* so dev and prod converge.
    """
    logger = logging.getLogger(__name__)
    from tracker_core.store.tenant_db_manager import tenant_db_manager

    if database_url in tenant_db_manager.migrated_urls:
        logger.debug("Database %s already migrated in this runtime", database_url)
        return

    from alembic import command
    from alembic.config import Config

    from . import models  # noqa: F401  ensure models imported

    logger.info("Loading core alembic config")
    cfg_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("script_location", str(cfg_path.parent / "alembic" / "core_alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    logger.info("Running core alembic upgrade on URL: %s", database_url)
    # Alembic is sync; run in a thread so we don't block the loop on startup.
    import asyncio as _asyncio

    await _asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("Core Alembic upgrade complete")

    if database_url.startswith("sqlite"):
        # Explicitly enforce the partial unique constraint in SQLite too
        temp_engine = create_async_engine(
            database_url,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        temp_sessionmaker = async_sessionmaker(temp_engine, expire_on_commit=False, class_=AsyncSession)
        async with temp_sessionmaker() as s:
            await s.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_trips_one_ongoing_per_device "
                    "ON trips(device_id) WHERE ended_at IS NULL;",
                ),
            )
            await s.commit()
        await temp_engine.dispose()

    tenant_db_manager.migrated_urls.add(database_url)
