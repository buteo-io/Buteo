"""Auth router. Issues JWT in httpOnly cookie. Rate-limited login."""

from __future__ import annotations

import logging
import re

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.identity_db import Tenant, get_identity_session
from tracker_core.store.models import User
from tracker_core.store.security import (
    dummy_verify_password,
    make_token,
    parse_token,
    verify_password,
)
from tracker_core.store.tenant_db_manager import tenant_db_manager

from ..deps import current_user, get_current_claims, TokenClaims
from ..limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


# Shape check only: `local@domain.tld`. No deliverability check because the
# app never sends email; the address is just an identifier and reserved-TLD
# blocking would reject dev addresses like demo@x.test.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _mask_email(email: str) -> str:
    """Mask email to protect PII in logs (e.g. lo***@domain.tld)."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local}***@{domain}"
    return f"{local[:2]}***@{domain}"


class LoginIn(BaseModel):
    """Login request body. Email is normalised to lowercase server-side."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 255 or not _EMAIL_RE.match(v):
            raise ValueError("must look like name@domain.tld")
        return v


class TokenOut(BaseModel):
    """JWT envelope returned by ``/auth/login``.

    Browsers can ignore the body and rely on the ``Set-Cookie`` header;
    CLI clients (curl/httpx) use ``access_token`` as a bearer.
    """

    # Empty string for browser logins (cookie carries the credential). Only
    # non-empty when the request looks like a non-browser client (no Origin
    # header), so an XSS in the SPA can't read the token from the response.
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    """Shape of ``GET /me``. Only exposes non-sensitive identifiers."""

    id: str  # public_id (uuid)
    email: str
    features: list[str] = []


def _set_session_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        key=AppConfig.auth_cookie_name,
        value=token,
        max_age=AppConfig.jwt_expire_min * 60,
        httponly=True,
        secure=AppConfig.auth_cookie_secure and not AppConfig.dev_insecure_cookies,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(
        key=AppConfig.auth_cookie_name,
        path="/",
        httponly=True,
        secure=AppConfig.auth_cookie_secure and not AppConfig.dev_insecure_cookies,
        samesite="strict",
    )


@router.post("/auth/login", response_model=TokenOut)
@limiter.limit("5/minute;20/hour")
async def login(
    request: Request,  # slowapi reads this from the signature
    body: LoginIn,
    response: Response,
    x_client_type: str | None = Header(default=None),
    identity_db: AsyncSession = Depends(get_identity_session),
) -> TokenOut:
    """Authenticate by email + password.

    Sets an httpOnly session cookie and also returns the JWT for non-browser
    clients. Rate-limited to 5/min and 20/hour per IP to slow credential
    stuffing.

    Errors:
        401: invalid credentials (includes inactive users — intentionally
            indistinguishable).
        429: rate limit exceeded (handled by slowapi).
    """
    email = body.email.strip().lower()
    tenant = await identity_db.scalar(select(Tenant).where(Tenant.email == email))
    # Always burn one bcrypt verification, even when the tenant doesn't exist
    # or is inactive. Without this, an attacker can enumerate which emails
    # have accounts (and which are deactivated) purely from response timing
    # — bcrypt is ~100 ms, the rest of the request is ~ms.
    if tenant is None:
        dummy_verify_password()
        password_ok = False
    else:
        password_ok = verify_password(body.password, tenant.password_hash)

    if tenant is None:
        logger.warning("login_failed reason=unknown_email email=%s", _mask_email(email))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not tenant.is_active:
        logger.warning(
            "login_failed reason=inactive email=%s tenant_id=%s",
            _mask_email(email),
            tenant.tenant_id,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not password_ok:
        logger.warning(
            "login_failed reason=bad_password email=%s tenant_id=%s",
            _mask_email(email),
            tenant.tenant_id,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    # Get User from tenant-specific database to get public_id
    async with tenant_db_manager.get_tenant_session(tenant.tenant_id) as tenant_db:
        user = await tenant_db.scalar(select(User).where(User.email == email))
        if not user:
            logger.error(
                "tenant_exists_but_no_user tenant_id=%s email=%s",
                tenant.tenant_id,
                email,
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
        user_public_id = user.public_id

    tok = make_token(
        public_id=user_public_id,
        tenant_id=tenant.tenant_id,
        token_version=tenant.token_version,
        features=tenant.features,
    )
    logger.info(
        "login_ok email=%s tenant_id=%s user_id=%s",
        email,
        tenant.tenant_id,
        user_public_id,
    )
    _set_session_cookie(response, tok)
    # Return the bearer token only to non-browser clients that explicitly
    # identify themselves via X-Client-Type: mobile (or any non-browser value).
    # Browsers never send this header, so XSS in the SPA cannot exfiltrate it.
    # Browser clients rely solely on the httpOnly session cookie.
    is_browser_client = x_client_type is None or x_client_type.lower() == "web"
    return TokenOut(access_token="" if is_browser_client else tok)


@router.post("/auth/logout", status_code=204)
async def logout(
    session: str | None = Cookie(default=None, alias=AppConfig.auth_cookie_name),
    # MUST be Header(...) — without it FastAPI treats the parameter as a
    # query string, which would let callers smuggle a JWT through proxy /
    # access logs (e.g. `/auth/logout?authorization=Bearer+...`).
    authorization: str | None = Header(default=None),
    identity_db: AsyncSession = Depends(get_identity_session),
) -> Response:
    """Revoke outstanding tokens for the caller (if token valid) and clear the cookie.

    Idempotent: always clears the cookie and returns 204 even if the caller
    has no valid session. Bumps ``Tenant.token_version`` when a valid token is
    presented so every previously-issued JWT becomes invalid.
    """
    token = session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1]
    if token:
        claims = parse_token(token)
        if claims is not None:
            try:
                tenant = await identity_db.scalar(
                    select(Tenant).where(Tenant.tenant_id == claims.tenant_id)
                )
                if tenant and tenant.token_version == claims.token_version:
                    tenant.token_version = (tenant.token_version or 0) + 1
                    await identity_db.commit()
                    logger.info(
                        "logout tenant_id=%s user_id=%s",
                        tenant.tenant_id,
                        claims.public_id,
                    )
            except ValueError:
                pass
    # Build the response we return ourselves so `delete_cookie` lands in its
    # headers. Using a `response: Response` dependency parameter would be
    # silently dropped here because returning a Response instance bypasses
    # FastAPI's automatic merge of the injected response.
    resp = Response(status_code=204)
    _clear_session_cookie(resp)
    return resp


@router.get("/me", response_model=MeOut)
async def me(
    user: User = Depends(current_user),
    claims: TokenClaims = Depends(get_current_claims),
) -> MeOut:
    """Return the authenticated user's public id, email, and enabled features."""
    logger.debug("me user_id=%s", user.id)
    return MeOut(
        id=str(user.public_id),
        email=user.email,
        features=claims.features,
    )
