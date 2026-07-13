"""Password hashing + JWT helpers.

JWT claims used:
    sub  - user.public_id (UUID string)
    iss  - settings.jwt_issuer
    aud  - settings.jwt_audience
    iat  - issued at
    exp  - expiry
    jti  - random per-token id (for revocation/audit lists later)
    ver  - User.token_version snapshot; mismatch = revoked
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import bcrypt
from jose import JWTError, jwt

from tracker_core.internal.appctx.config import AppConfig

from .ids import PrefixUUID


def hash_password(p: str) -> str:
    """Return a bcrypt hash of ``p``. Suitable for storing in ``users.password_hash``."""
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    """Return True if plaintext ``p`` matches previously-hashed ``h``."""
    return bcrypt.checkpw(p.encode(), h.encode())


@lru_cache(maxsize=1)
def _get_dummy_password_hash() -> str:
    """Pre-compute bcrypt hash on-demand and cache it for timing consistency."""
    return bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode()


def dummy_verify_password() -> None:
    """Run a bcrypt verify against a throwaway hash for constant-time login.

    Login handlers MUST call this on the unknown-email branch so the
    response time of "no such user" matches "wrong password". Without it,
    an attacker can enumerate which emails have accounts purely by timing
    `/auth/login` (~100 ms diff between branches).
    """
    bcrypt.checkpw(b"dummy-password-for-timing", _get_dummy_password_hash().encode())


def make_token(
    *,
    public_id: PrefixUUID,
    tenant_id: PrefixUUID,
    token_version: int,
    features: list[str] | None = None,
) -> str:
    """Issue a signed JWT for a user.

    Args:
        public_id: The user's ``public_id`` UUID; becomes the ``sub`` claim.
        tenant_id: The identifier of the user's active tenant.
        token_version: Snapshot of ``User.token_version`` at issue time. The
            auth dependency rejects the token if this drifts from the live
            value, which is how logout/password-reset revoke old token.
        features: Optional list of enabled feature flags for the tenant.

    Returns:
        The encoded JWT string.
    """
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": str(public_id),
        "iss": AppConfig.jwt_issuer,
        "aud": AppConfig.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=AppConfig.jwt_expire_min),
        "jti": uuid.uuid4().hex,
        "ver": token_version,
        "tenant_id": tenant_id,
        "features": features or [],
    }
    return jwt.encode(payload, AppConfig.jwt_secret, algorithm=AppConfig.jwt_alg)


class TokenClaims:
    """Lightweight value object for the subset of claims we act on."""

    __slots__ = ("features", "jti", "public_id", "tenant_id", "token_version")

    def __init__(
        self,
        public_id: PrefixUUID,
        tenant_id: PrefixUUID,
        token_version: int,
        jti: str,
        features: set[str],
    ) -> None:
        self.public_id = public_id
        self.tenant_id = tenant_id
        self.token_version = token_version
        self.jti = jti
        self.features = features


def parse_token(token: str) -> TokenClaims | None:
    """Decode + verify a JWT. Returns :class:`TokenClaims` or ``None`` on any failure.

    Reasons for ``None``: bad signature, wrong issuer/audience, expired,
    malformed, missing required claim. Callers must treat ``None`` as 401.
    """
    try:
        data = jwt.decode(
            token,
            AppConfig.jwt_secret,
            algorithms=[AppConfig.jwt_alg],
            audience=AppConfig.jwt_audience,
            issuer=AppConfig.jwt_issuer,
        )
        return TokenClaims(
            public_id=str(data["sub"]),
            tenant_id=str(data.get("tenant_id", "")),
            token_version=int(data.get("ver", 0)),
            jti=str(data.get("jti", "")),
            features=set(data.get("features", [])),
        )
    except (JWTError, KeyError, ValueError):
        return None


def hash_share_token(token: str) -> str:
    """Return stable SHA-256 digest for public share tokens.

    Uses dedicated pepper when configured, otherwise falls back to JWT secret
    so deployments get a non-empty secret without extra setup.
    """
    pepper = AppConfig.share_token_pepper or AppConfig.jwt_secret
    return hashlib.sha256(f"{pepper}:{token}".encode()).hexdigest()
