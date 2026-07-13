"""FastAPI application factory.

:func:`create_app` wires:

- rate limiting (``slowapi``) for the auth router
- CORS with credentials (cookie-based auth)
- all domain routers under their canonical prefixes
- a ``/healthz`` probe that also checks DB reachability
- Alembic migrations on startup via :func:`tracker_core.store.identity_db.init_identity_db` and :func:`tracker_core.store.core_db.init_core_db`

The app title + version surface in the auto-generated OpenAPI document at
``/docs`` and ``/openapi.json`` — those are the canonical API reference.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from tracker_core.custom_logger import configure_logging
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.identity_db import IdentitySessionLocal, init_identity_db

from .limiter import limiter
from .routers import (
    analytics,
    auth,
    devices,
    entities,
    media,
    overnight_spots,
    places,
    positions,
    public_share,
    share_links,
    trips,
)

configure_logging(AppConfig.log_level, debug=AppConfig.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run Alembic migrations on startup so dev + prod share one schema path."""
    try:
        await init_identity_db()
    except Exception:
        logger.exception("startup_failed_init_identity_db")
        raise
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A fully-wired :class:`FastAPI` app. Safe to call multiple times; each
        invocation yields a fresh instance (used by tests).
    """
    # Docs/openapi are disabled in prod (DOCS_ENABLED=false) so the route
    # surface isn't advertised to drive-by scanners. Tests & dev keep them.
    docs_kwargs: dict = {}
    if not AppConfig.docs_enabled:
        docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(
        title="Tracker API",
        version="0.1.0",
        lifespan=lifespan,
        **docs_kwargs,
    )

    # Rate limiter (slowapi) — shared instance used by auth.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=AppConfig.cors_list,
        # Cookie-based auth needs credentials; browsers also enforce that
        # allow_origins must NOT be "*" when credentials=True (we use a list).
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - t0) * 1000)
        client = request.headers.get(
            "x-forwarded-for",
            request.client.host if request.client else "-",
        )
        path = request.url.path
        if path.startswith("/share/"):
            path = "/share/[redacted]"
        logger.info(
            "http_access",
            extra={
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "ms": ms,
                "client": client,
            },
        )
        # Slide session cookie on successful authenticated requests so the
        # PWA stays logged in as long as the user is active. 401 responses
        # (expired / invalid token) skip sliding — user must re-login.
        # Skip sliding on login/logout so we don't overwrite new or cleared cookies.
        if 200 <= response.status_code < 400 and request.url.path.rstrip("/") not in (
            "/auth/login",
            "/auth/logout",
        ):
            session_cookie = request.cookies.get(AppConfig.auth_cookie_name)
            if session_cookie:
                response.set_cookie(
                    key=AppConfig.auth_cookie_name,
                    value=session_cookie,
                    max_age=AppConfig.jwt_expire_min * 60,
                    httponly=True,
                    secure=AppConfig.auth_cookie_secure and not AppConfig.dev_insecure_cookies,
                    samesite="strict",
                    path="/",
                )
        return response

    app.include_router(auth.router, tags=["auth"])
    app.include_router(devices.router, tags=["devices"])
    app.include_router(entities.router, tags=["entities"])
    app.include_router(positions.router, tags=["positions"])
    app.include_router(places.router, tags=["places"])
    app.include_router(analytics.router, tags=["analytics"])
    app.include_router(trips.router, tags=["trips"])
    app.include_router(overnight_spots.router, tags=["overnight-spots"])
    app.include_router(share_links.router, tags=["share-links"])
    app.include_router(public_share.router, tags=["public"])
    app.include_router(media.router, tags=["media"])

    # Load dynamic plugins
    from .plugins.loader import load_plugins

    load_plugins(app)

    @app.get("/healthz")
    async def healthz() -> dict:
        """Liveness + DB reachability probe. 200 when reachable, 503 otherwise.

        Never returns the underlying error string to the client — that would
        leak DSN fragments / driver details. Full exception is logged.
        """
        try:
            async with IdentitySessionLocal() as db:
                await db.execute(text("SELECT 1"))
        except Exception:
            logger.exception("healthz_db_unreachable")
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail="db unavailable") from None
        return {"ok": True, "db": "up"}

    return app


app = create_app()
logger.info(
    "API server started",
    extra={"host": AppConfig.api_host, "port": AppConfig.api_port},
)
