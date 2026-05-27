"""Shared test fixtures.

Sets required env vars before any tracker_core imports and provides
DB-level fixtures (user + device provisioning) shared across all test suites.
"""

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy import delete

os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DEV_INSECURE_COOKIES", "true")

from api.main import create_app as _create_api_app
from api.routers import auth as _auth_module
from ingest.osmand import api as _osmand_module
from ingest.osmand.api import create_app as _create_osmand_app
from tracker_core.store.core_db import init_core_db
from tracker_core.store.identity_db import (
    GPSDevice,
    IdentitySessionLocal,
    Tenant,
    init_identity_db,
)
from tracker_core.store.models import Device, Entity, User
from tracker_core.store.security import hash_password
from tracker_core.store.tenant_db_manager import tenant_db_manager

# Tests fire many requests in tight loops — flip both per-IP limiters off
# so we test behavior rather than rate-limit timing.
_auth_module.limiter.enabled = False
_osmand_module._limiter.enabled = False


@dataclass(slots=True)
class Account:
    """Convenience bundle for a freshly-provisioned test account."""

    email: str
    password: str
    user_id: int
    device_imei: str
    device_id: int
    device_pid: str
    tenant_id: str


def _unique_imei() -> str:
    return f"{uuid.uuid4().int % 10**15:015d}"


async def _provision(email: str, password: str = "pw1234abcd!!") -> Account:
    """Create a user + device pair, returning the identifiers tests need."""
    await init_identity_db()
    tenant_id = f"test_tenant_{email.replace('@', '_').replace('.', '_')}"

    # Clean up existing test database file if any
    from pathlib import Path

    from tracker_core.internal.appctx.config import AppConfig

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
        if db_file.exists():
            try:
                db_file.unlink()
            except OSError:
                pass

    # 1. Register Tenant in Identity DB
    async with IdentitySessionLocal() as id_s:
        await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
        await id_s.commit()

        tenant = Tenant(
            tenant_id=tenant_id,
            email=email,
            password_hash=hash_password(password),
            database_type="sqlite",
            database_name=f"tnt{tenant_id}.db",
        )
        id_s.add(tenant)
        await id_s.commit()

    # 2. Run core schema migrations on dynamic tenant database URL
    tenant_url = tenant_db_manager.get_tenant_url(tenant_id)
    await init_core_db(tenant_url)

    # 3. Create local User and Device inside the dynamic tenant database
    imei = _unique_imei()
    async with tenant_db_manager.get_tenant_session(tenant_id) as s:
        u = User(email=email, password_hash=hash_password(password))
        s.add(u)
        await s.flush()
        ent = Entity(user_id=u.id, type="vehicle", name="Campervan")
        s.add(ent)
        await s.flush()
        d = Device(entity_id=ent.id, imei=imei, name=f"Camper-{imei[-4:]}")
        s.add(d)
        await s.commit()
        await s.refresh(u)
        await s.refresh(d)

    # 4. Create GPSDevice routing in central Identity DB
    async with IdentitySessionLocal() as id_s:
        gps_device = GPSDevice(
            imei=imei,
            tenant_id=tenant_id,
        )
        id_s.add(gps_device)
        await id_s.commit()

    return Account(
        email=email,
        password=password,
        user_id=u.id,
        device_imei=imei,
        device_id=d.id,
        device_pid=d.public_id,
        tenant_id=tenant_id,
    )


async def _purge(tenant_id: str) -> None:
    """Delete the tenant; all owned rows and devices cascade away."""
    # 1. Clear cached engines so no active locks / open connections exist
    await tenant_db_manager.clear_cache()

    # 2. Delete Tenant from Identity DB (cascades to GPS Devices)
    async with IdentitySessionLocal() as id_s:
        await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
        await id_s.commit()

    # 3. Clean up tenant database file from disk
    from pathlib import Path

    from tracker_core.internal.appctx.config import AppConfig

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
        if db_file.exists():
            try:
                db_file.unlink()
            except OSError:
                pass


@pytest.fixture
async def account() -> AsyncIterator[Account]:
    """Primary test account. Cleaned up after the test."""
    acc = await _provision("alice@test.example")
    from tracker_core.store.tenant_db_manager import current_tenant_id

    token = current_tenant_id.set(acc.tenant_id)
    try:
        yield acc
    finally:
        current_tenant_id.reset(token)
        await _purge(acc.tenant_id)


@pytest.fixture
async def other_account() -> AsyncIterator[Account]:
    """Second account for cross-tenant isolation tests."""
    acc = await _provision("bob@test.example")
    from tracker_core.store.tenant_db_manager import current_tenant_id

    token = current_tenant_id.set(acc.tenant_id)
    try:
        yield acc
    finally:
        current_tenant_id.reset(token)
        await _purge(acc.tenant_id)


async def _do_login(c: httpx.AsyncClient, email: str, password: str) -> None:
    """Log in by replaying the same flow a browser would.

    The auth router only returns a non-empty bearer token when the request
    advertises itself as non-browser (``X-Client-Type`` other than ``web``)
    — see ``api/routers/auth.py``. In tests we deliberately exercise the
    *browser* path so the session cookie carries auth, matching what the
    SPA does in production. ``httpx.AsyncClient`` keeps a cookie jar across
    requests automatically, so subsequent calls on the same client are
    authenticated.
    """
    r = await c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    # Ensure the cookie really landed in the jar — without this the rest
    # of the suite would silently fall back to anonymous.
    assert any(ck.name == "tracker_session" for ck in c.cookies.jar)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Unauthenticated client pointing at the main API app."""
    app = _create_api_app()

    from api.deps import require_feature

    @app.get("/test-premium-route", dependencies=[require_feature("premium_analytics")])
    def premium_route():
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def authed(
    client: httpx.AsyncClient, account: Account
) -> AsyncIterator[httpx.AsyncClient]:
    """Client logged in as :func:`account` via the cookie path."""
    await _do_login(client, account.email, account.password)
    return client


@pytest.fixture
async def other_authed(other_account: Account) -> AsyncIterator[httpx.AsyncClient]:
    """Independent client for the *other* account, used in 404-on-foreign tests."""
    app = _create_api_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        await _do_login(c, other_account.email, other_account.password)
        yield c


@pytest.fixture
async def osmand_client() -> AsyncIterator[httpx.AsyncClient]:
    """Unauthenticated client pointing at the OsmAnd ingest app."""
    app = _create_osmand_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
