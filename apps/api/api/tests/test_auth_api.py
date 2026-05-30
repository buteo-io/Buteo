"""End-to-end auth tests: login, /me, logout, rate-limit boundary."""

from __future__ import annotations

import httpx

from .conftest import Account


async def test_login_sets_cookie_and_returns_token(
    client: httpx.AsyncClient,
    account: Account,
):
    """Default (browser) login: cookie set, but bearer token withheld.

    The auth router intentionally returns ``access_token = ""`` to clients
    that don't opt out of browser-mode via ``X-Client-Type``, so an XSS in
    the SPA can't exfiltrate the JWT. A non-browser client opting in is
    covered by ``test_logout_invalidates_old_bearer``.
    """
    r = await client.post(
        "/auth/login",
        json={"email": account.email, "password": account.password},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    # Browser-mode: token deliberately blank.
    assert body["access_token"] == ""
    # Cookie must be set + httpOnly equivalent (httpx exposes it via cookies jar).
    assert any(c.name == "tracker_session" for c in r.cookies.jar)


async def test_login_returns_token_for_non_browser_client(
    client: httpx.AsyncClient,
    account: Account,
):
    """Opt-in: ``X-Client-Type: cli`` (any non-``web`` value) gets a bearer."""
    r = await client.post(
        "/auth/login",
        json={"email": account.email, "password": account.password},
        headers={"X-Client-Type": "cli"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_email_normalisation(
    client: httpx.AsyncClient,
    account: Account,
):
    # Mixed-case email must still resolve.
    r = await client.post(
        "/auth/login",
        json={"email": account.email.upper(), "password": account.password},
    )
    assert r.status_code == 200


async def test_login_invalid_password(client: httpx.AsyncClient, account: Account):
    r = await client.post(
        "/auth/login",
        json={"email": account.email, "password": "wrong-password"},
    )
    assert r.status_code == 401


async def test_login_unknown_user(client: httpx.AsyncClient):
    r = await client.post(
        "/auth/login",
        json={"email": "ghost@test.example", "password": "doesnt-matter-12"},
    )
    assert r.status_code == 401


async def test_login_invalid_email_shape(client: httpx.AsyncClient):
    r = await client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "whatever12345"},
    )
    assert r.status_code == 422


async def test_me_unauthenticated_is_401(client: httpx.AsyncClient):
    r = await client.get("/me")
    assert r.status_code == 401


async def test_me_after_login_returns_account(authed: httpx.AsyncClient, account: Account):
    r = await authed.get("/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == account.email
    # public_id is a UUID string
    assert "-" in body["id"]
    assert "features" in body
    assert body["features"] == []


async def test_me_returns_tenant_features(client: httpx.AsyncClient, account: Account):
    from tracker_core.store.identity_db import IdentitySessionLocal, Tenant
    from sqlalchemy import select

    # 1. Update tenant features in central DB
    async with IdentitySessionLocal() as id_s:
        tenant = await id_s.scalar(select(Tenant).where(Tenant.tenant_id == account.tenant_id))
        assert tenant is not None
        tenant.features = ["plugin_weather", "premium_analytics"]
        await id_s.commit()

    # 2. Log in with the updated tenant
    r_login = await client.post(
        "/auth/login",
        json={"email": account.email, "password": account.password},
    )
    assert r_login.status_code == 200

    # 3. Request /me and verify features are present
    r_me = await client.get("/me")
    assert r_me.status_code == 200
    body = r_me.json()
    assert body["email"] == account.email
    assert body["features"] == ["plugin_weather", "premium_analytics"]


async def test_logout_invalidates_old_bearer(
    client: httpx.AsyncClient,
    account: Account,
):
    # Ask the server for a real bearer (default browser-mode returns "").
    r = await client.post(
        "/auth/login",
        json={"email": account.email, "password": account.password},
        headers={"X-Client-Type": "cli"},
    )
    token = r.json()["access_token"]
    assert token, "non-browser client must receive a bearer token"
    # session cookie is on `client` automatically.
    assert (await client.get("/me")).status_code == 200
    assert (await client.post("/auth/logout")).status_code == 204
    # The old bearer should no longer be honoured (token_version bumped).
    r3 = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 401


async def test_logout_clears_session_cookie(
    client: httpx.AsyncClient,
    account: Account,
):
    """Regression: /auth/logout must emit Set-Cookie with Max-Age=0.

    Bumping token_version revokes the JWT server-side, but if the cookie
    isn't actively cleared the browser keeps replaying the (now invalid)
    cookie until natural expiry, leaving the user wedged on /me 401s.
    """
    r = await client.post(
        "/auth/login",
        json={"email": account.email, "password": account.password},
    )
    assert r.status_code == 200
    logout = await client.post("/auth/logout")
    assert logout.status_code == 204
    # Starlette emits "set-cookie" headers for delete_cookie. There must be
    # one for our session cookie, with an empty value or Max-Age=0.
    set_cookies = [v for k, v in logout.headers.items() if k.lower() == "set-cookie"]
    cleared = [c for c in set_cookies if c.startswith("tracker_session=")]
    assert cleared, f"no Set-Cookie for tracker_session in {set_cookies}"
    cookie = cleared[0].lower()
    assert "max-age=0" in cookie or 'tracker_session=""' in cookie or "tracker_session=;" in cookie


async def test_require_feature_dependency(
    client: httpx.AsyncClient,
    authed: httpx.AsyncClient,
    account: Account,
) -> None:
    from tracker_core.store.identity_db import IdentitySessionLocal, Tenant
    from sqlalchemy import select
    from api.main import create_app

    # 1. Unauthenticated request -> 401 (use a clean client to avoid cookie sharing with authed)
    app = create_app()
    from api.deps import require_feature

    @app.get("/test-premium-route", dependencies=[require_feature("premium_analytics")])
    def premium_route():
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as unauth_client:
        r_unauth = await unauth_client.get("/test-premium-route")
        assert r_unauth.status_code == 401, r_unauth.text

    # 2. Authenticated but lacking feature -> 403
    r_no_feat = await authed.get("/test-premium-route")
    assert r_no_feat.status_code == 403
    assert "locked" in r_no_feat.text

    # 3. Simulate granting feature and bumping token_version
    async with IdentitySessionLocal() as id_s:
        tenant = await id_s.scalar(select(Tenant).where(Tenant.tenant_id == account.tenant_id))
        assert tenant is not None
        tenant.features = ["premium_analytics"]
        tenant.token_version = (tenant.token_version or 0) + 1
        await id_s.commit()

    # Old authed token is now revoked -> 401
    r_revoked = await authed.get("/test-premium-route")
    assert r_revoked.status_code == 401

    # 4. Log in again to get fresh JWT containing features
    r_login = await client.post(
        "/auth/login",
        json={"email": account.email, "password": account.password},
    )
    assert r_login.status_code == 200

    # Request premium route with new token -> 200
    r_success = await client.get("/test-premium-route")
    assert r_success.status_code == 200
    assert r_success.json() == {"status": "ok"}

    # 5. Deactivate tenant -> 401
    async with IdentitySessionLocal() as id_s:
        tenant = await id_s.scalar(select(Tenant).where(Tenant.tenant_id == account.tenant_id))
        assert tenant is not None
        tenant.is_active = False
        await id_s.commit()

    r_deactivated = await client.get("/test-premium-route")
    assert r_deactivated.status_code == 401

