import os

# Set required env vars BEFORE importing app modules.
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DEV_INSECURE_COOKIES", "true")

import httpx
import pytest
from api.main import create_app
from sqlalchemy import delete
from tracker_core.store.models import User
from tracker_core.store.security import hash_password


@pytest.fixture
async def client():
    from tracker_core.store.core_db import init_core_db
    from tracker_core.store.identity_db import (
        IdentitySessionLocal,
        Tenant,
        init_identity_db,
    )
    from tracker_core.store.tenant_db_manager import tenant_db_manager

    await init_identity_db()
    tenant_id = "test_tenant_auth"

    # Register tenant in Identity DB
    async with IdentitySessionLocal() as id_s:
        await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
        await id_s.commit()
        tenant = Tenant(
            tenant_id=tenant_id,
            email="test@example.com",
            password_hash=hash_password("pw1234abcd!!"),
            database_type="sqlite",
            database_name=f"test_tenant_{tenant_id}.db",
        )
        id_s.add(tenant)
        await id_s.commit()

    # Migrate tenant database
    tenant_url = tenant_db_manager.get_tenant_url(tenant_id)
    await init_core_db(tenant_url)

    # Create local User inside dynamic database
    async with tenant_db_manager.get_tenant_session(tenant_id) as s:
        await s.execute(delete(User).where(User.email == "test@example.com"))
        s.add(
            User(email="test@example.com"),
        )
        await s.commit()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        try:
            yield c
        finally:
            await tenant_db_manager.clear_cache()
            async with IdentitySessionLocal() as id_s:
                await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
                await id_s.commit()


async def test_login_and_me(client: httpx.AsyncClient):
    r = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "pw1234abcd!!"},
    )
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    # cookie path
    r2 = await client.get("/me")  # cookie auto-attached by httpx jar
    assert r2.status_code == 200
    assert r2.json()["email"] == "test@example.com"
    # bearer path
    r3 = await client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert r3.status_code == 200


async def test_login_bad(client: httpx.AsyncClient):
    r = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrong"},
    )
    assert r.status_code == 401


async def test_login_email_case_insensitive(client: httpx.AsyncClient):
    r = await client.post(
        "/auth/login",
        json={"email": "TEST@Example.COM", "password": "pw1234abcd!!"},
    )
    assert r.status_code == 200, r.text


async def test_me_unauth(client: httpx.AsyncClient):
    r = await client.get("/me")
    assert r.status_code == 401


async def test_logout_invalidates_old_token(client: httpx.AsyncClient):
    r = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "pw1234abcd!!"},
    )
    tok = r.json()["access_token"]
    # logout
    r2 = await client.post("/auth/logout")
    assert r2.status_code == 204
    # old bearer token should now be rejected (token_version bumped)
    r3 = await client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert r3.status_code == 401
