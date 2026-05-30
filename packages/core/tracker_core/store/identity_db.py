"""Async SQLAlchemy engine + session factory + Alembic bootstrap for Identity DB.

Exposes:
    - :class:`IdentityBase` — declarative base for identity models.
    - :class:`Tenant` — tenant model mapping tenants to DBs.
    - :class:`GPSDevice` — GPS device model mapping IMEI to tenants.
    - :data:`identity_engine` / :data:`IdentitySessionLocal` — engine and session maker.
    - :func:`get_identity_session` — FastAPI dependency yielding AsyncSession.
    - :func:`init_identity_db` — runs identity Alembic migrations to head.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool, StaticPool

from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.ids import gen_tenant_id

_SQLITE_BUSY_TIMEOUT_MS = 6_000


class IdentityBase(DeclarativeBase):
    """Declarative base shared by every ORM model in identity database."""


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Tenant(IdentityBase):
    """Identity tenant registration. Maps tenants to credentials and databases."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False, default=gen_tenant_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    database_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'sqlite' or 'postgresql'
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    __table_args__ = (CheckConstraint("email = lower(email)", name="tenants_email_lowercase"),)


class GPSDevice(IdentityBase):
    """Routes device telemetry to specific tenants based on device IMEI."""

    __tablename__ = "gps_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imei: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


def _make_identity_engine():
    url = AppConfig.identity_database_url
    if url.startswith("sqlite"):
        eng = create_async_engine(
            url,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(eng.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
            cursor.close()

        return eng
    return create_async_engine(url, future=True, poolclass=NullPool)


identity_engine = _make_identity_engine()
IdentitySessionLocal = async_sessionmaker(identity_engine, expire_on_commit=False, class_=AsyncSession)


async def get_identity_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session scoped to one request."""
    async with IdentitySessionLocal() as session:
        yield session


async def init_identity_db() -> None:
    """Run identity Alembic migrations to head. Idempotent."""
    logger = logging.getLogger(__name__)
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    logger.info("Loading identity alembic config")
    cfg_path = Path(__file__).resolve().parent.parent / "identity_alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("script_location", str(cfg_path.parent / "alembic" / "identity_alembic"))
    cfg.set_main_option("sqlalchemy.url", AppConfig.identity_database_url)
    logger.info("Running identity alembic upgrade")
    import asyncio as _asyncio

    await _asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("Identity Alembic upgrade complete")
