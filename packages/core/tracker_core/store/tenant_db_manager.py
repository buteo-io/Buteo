"""Tenant-specific dynamic database connection routing and session management."""

import asyncio
import contextvars
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from tracker_core.internal.appctx.config import AppConfig

logger = logging.getLogger(__name__)
_SQLITE_BUSY_TIMEOUT_MS = 6_000

# Request/test context variable carrying active tenant_id
current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_tenant_id", default=None)


class TenantDatabaseManager:
    """Manages cached database engines and session makers per tenant."""

    def __init__(self) -> None:
        self._engines: dict[str, AsyncEngine] = {}
        self._sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}
        self.migrated_urls: set[str] = set()
        self._migration_locks: dict[str, asyncio.Lock] = {}

    async def clear_cache(self) -> None:
        """Dispose all cached engines and clear caches."""
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        self._sessionmakers.clear()
        self.migrated_urls.clear()
        self._migration_locks.clear()

    def get_tenant_url(self, tenant_id: str) -> str:
        """Resolve database URL for a tenant based on AppConfig.database_type."""
        db_type = AppConfig.database_type.strip().lower()
        if db_type == "sqlite":
            if not AppConfig.data_dir:
                raise ValueError("data_dir must be specified when using SQLite")
            # Ensure parent directory exists
            Path(AppConfig.data_dir).mkdir(parents=True, exist_ok=True)
            return f"sqlite+aiosqlite:///{AppConfig.data_dir}/tnt{tenant_id}.db"

        return (
            f"postgresql+asyncpg://{AppConfig.postgres_user}:{AppConfig.postgres_password}"
            f"@{AppConfig.postgres_db_host}:{AppConfig.postgres_db_port}/tracker_tenant_{tenant_id}"
        )

    def get_tenant_engine(self, tenant_id: str) -> AsyncEngine:
        """Get or create cached async engine for tenant."""
        if tenant_id in self._engines:
            return self._engines[tenant_id]

        url = self.get_tenant_url(tenant_id)
        logger.info("Creating dynamic engine for tenant %s (type: %s)", tenant_id, AppConfig.database_type)

        if url.startswith("sqlite"):
            engine = create_async_engine(
                url,
                future=True,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(engine.sync_engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, _connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
                cursor.close()
        else:
            engine = create_async_engine(url, future=True, poolclass=NullPool)

        self._engines[tenant_id] = engine
        return engine

    def get_tenant_sessionmaker(self, tenant_id: str) -> async_sessionmaker[AsyncSession]:
        """Get or create cached sessionmaker for tenant."""
        if tenant_id in self._sessionmakers:
            return self._sessionmakers[tenant_id]

        engine = self.get_tenant_engine(tenant_id)
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        self._sessionmakers[tenant_id] = maker
        return maker

    async def ensure_migrated(self, tenant_id: str) -> None:
        """Ensure core database migrations are run for this tenant (only once per runtime)."""
        url = self.get_tenant_url(tenant_id)
        if url in self.migrated_urls:
            return

        lock = self._migration_locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            if url in self.migrated_urls:
                return

            from tracker_core.store.core_db import init_core_db

            logger.info("Auto-migrating core database for tenant %s", tenant_id)
            await init_core_db(url)

    @asynccontextmanager
    async def get_tenant_session(self, tenant_id: str) -> AsyncIterator[AsyncSession]:
        """Async context manager yielding session for tenant."""
        await self.ensure_migrated(tenant_id)
        maker = self.get_tenant_sessionmaker(tenant_id)
        async with maker() as session:
            yield session


async def get_tenant_by_imei(imei: str) -> str | None:
    """Resolve the active tenant_id for a given device IMEI from Identity DB."""
    from sqlalchemy import select

    from tracker_core.store.identity_db import GPSDevice, IdentitySessionLocal, Tenant

    async with IdentitySessionLocal() as id_db:
        gps_device = await id_db.scalar(select(GPSDevice).where(GPSDevice.imei == imei))
        if not gps_device:
            return None
        tenant = await id_db.scalar(select(Tenant).where(Tenant.tenant_id == gps_device.tenant_id))
        if not tenant or not tenant.is_active:
            return None
        return tenant.tenant_id


# Export global singleton
tenant_db_manager = TenantDatabaseManager()
