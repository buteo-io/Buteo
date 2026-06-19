"""Auth dependencies. Reads JWT from httpOnly cookie OR Authorization header."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.features import Feature
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.identity_db import Tenant, get_identity_session
from tracker_core.store.models import User
from tracker_core.store.security import TokenClaims, parse_token
from tracker_core.store.tenant_db_manager import tenant_db_manager

# Re-export ownership helpers so existing `from ..deps import own_device` works.
from .ownership import (  # noqa: F401
    own_device,
    own_place,
    own_trip,
)

_COOKIE_NAME = AppConfig.auth_cookie_name


def get_current_tenant_id(request: Request) -> str:
    """Resolve current tenant_id from request path parameter or JWT claims."""
    token_param = request.path_params.get("token")
    if token_param and "_" in token_param:
        if len(token_param) > 44 and token_param[-44] == "_":
            return token_param[:-44]
        return token_param.split("_", 1)[0]

    # 2. Try extracting tenant_id from JWT cookie/header
    authorization = request.headers.get("authorization")
    cookie = request.cookies.get(_COOKIE_NAME)
    token = _extract_token(authorization, cookie)
    if token:
        claims = parse_token(token)
        if claims and claims.tenant_id:
            return claims.tenant_id

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Could not resolve tenant id from token"
    )


async def get_db(
    tenant_id: str = Depends(get_current_tenant_id),
) -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` scoped to the current tenant's database.

    Closed on return. Resolves tenant_id dynamically from JWT or public share token.
    """
    from tracker_core.store.tenant_db_manager import current_tenant_id

    token = current_tenant_id.set(tenant_id)
    try:
        async with tenant_db_manager.get_tenant_session(tenant_id) as session:
            yield session
    finally:
        current_tenant_id.reset(token)


def _extract_token(authorization: str | None, cookie: str | None) -> str | None:
    """Pick the JWT from cookie first, then ``Authorization: Bearer ...`` header.

    Cookie precedence lets browsers use the session cookie even when CLI tools
    accidentally forward their own Authorization header. A malformed header
    such as ``Authorization: Bearer`` (no token) or ``Authorization: Bearer ``
    (only whitespace) used to raise ``IndexError`` here and bubble up as a
    500 — return ``None`` so the caller maps it to a clean 401.
    """
    if cookie:
        return cookie
    if authorization and authorization.lower().startswith("bearer "):
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[1]:
            return parts[1]
    return None


def get_current_claims(
    authorization: str | None = Header(default=None),
    session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
) -> TokenClaims:
    """Extract and parse JWT claims without DB validation."""
    token = _extract_token(authorization, session)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing credentials")
    claims = parse_token(token)
    if claims is None or not claims.tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return claims


def require_feature(*feature_names: Feature):
    """Return a FastAPI dependency that enforces the tenant has all ``feature_names`` in their JWT.

    Usage::

        @router.post("/", dependencies=[Depends(require_feature(Feature.SOME_FLAG))])
        @router.post("/", dependencies=[Depends(require_feature(Feature.FOO, Feature.BAR))])
    """

    def dependency(
        claims: TokenClaims = Depends(get_current_claims),
        _user: User = Depends(current_user),
    ) -> None:
        for feature_name in feature_names:
            if feature_name not in claims.features:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    f"Feature '{feature_name}' is not enabled for this account.",
                )

    return dependency


async def current_user(
    authorization: str | None = Header(default=None),
    session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
    identity_db: AsyncSession = Depends(get_identity_session),
) -> User:
    """Resolve the requesting user from JWT (cookie or bearer).

    Raises:
        HTTPException 401: no/invalid/revoked token or inactive user. The body
            never distinguishes "bad token" vs "user disabled" to avoid
            leaking account state.

    Returns:
        The authenticated :class:`User` ORM row.
    """
    token = _extract_token(authorization, session)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing credentials")
    claims = parse_token(token)
    if claims is None or not claims.tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    # 1. Verify Tenant in the central identity database
    tenant = await identity_db.scalar(
        select(Tenant).where(Tenant.tenant_id == claims.tenant_id)
    )
    if not tenant or not tenant.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "tenant inactive")
    if tenant.token_version != claims.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")

    try:
        from tracker_core.store.ids import validate_prefix_uuid

        validate_prefix_uuid(claims.public_id)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from None

    # 2. Query the user row inside the routed tenant database
    user = await db.scalar(select(User).where(User.public_id == claims.public_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user inactive")
    return user
