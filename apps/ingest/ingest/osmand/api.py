"""Traccar Client + OwnTracks HTTP ingest server.

Accepts GPS fixes from Traccar Client (OsmAnd protocol) and OwnTracks HTTP
mode. Device identifier is matched against :class:`Device.imei` — gate ingest
routes at the reverse proxy (TLS + IP
allow-list or VPN).

Request shape (per Traccar's ``OsmAndProtocolDecoder``):

- ``id``         device identifier (we map to IMEI). **required**
- ``lat``,``lon`` decimal degrees. **required**
- ``timestamp``  unix seconds (int/float) OR ISO 8601. Defaults to "now".
- ``speed``      knots — converted to km/h on store.
- ``altitude``   metres.

Traccar endpoint accepts both ``GET`` and ``POST`` (form-encoded body OR query
params). OwnTracks endpoint accepts ``POST`` JSON payloads.

Returns ``200 OK`` on success, ``400`` on bad payload, ``401`` on unknown
device, ``410`` on revoked device.
"""

from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .helpers import _ingest_one, _ingest_one_owntracks, _params

# Per-IP limiter. The OsmAnd endpoint is unauthenticated (the IMEI in the
# query string is the only credential), so without this anyone who learns
# an IMEI -- or even guesses one -- can flood the DB with synthetic fixes.
# 60/min is enough headroom for normal phone clients (Traccar Client / OsmAnd
# default is one fix every ~5-30 s) while clamping abusive bursts.
_limiter = Limiter(key_func=get_remote_address)

_router = APIRouter()


@_router.api_route("/traccar_client", methods=["GET", "POST"])
@_limiter.limit("150/minute;10000/hour")
async def traccar_client(request: Request) -> dict:
    """Accept a single Traccar/OsmAnd-protocol fix. Returns ``{"ok": true}``.

    Auth: the ``id`` param must equal a known, non-revoked :class:`Device`
    IMEI. There is no per-request token — gate this endpoint at the proxy.
    Per-IP rate limited (see ``_limiter``) to slow IMEI brute-forcing.
    """
    params = await _params(request)
    await _ingest_one(params)
    return {"ok": True}


@_router.post("/owntracks")
@_limiter.limit("150/minute;10000/hour")
async def owntracks(request: Request) -> list[object]:
    """Accept OwnTracks HTTP-mode JSON and return Recorder-style empty array.

    OwnTracks may POST payload types other than ``_type=location`` and may send
    empty payloads (e.g. friend deletion markers). These are accepted and
    ignored.
    """
    await _ingest_one_owntracks(request)
    return []


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan manager - no DB init needed (API handles migrations)."""
    yield


def create_app() -> FastAPI:
    """Build the OsmAnd ingest FastAPI application."""
    app = FastAPI(
        title="OsmAnd Ingest",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Wire slowapi: the limiter must hang off ``app.state`` for the
    # decorator to find it, and 429s need a JSON-shaped error body.
    app.state.limiter = _limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    import logging
    import time

    logger = logging.getLogger(__name__)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - t0) * 1000)
        client = request.headers.get(
            "x-forwarded-for", request.client.host if request.client else "-"
        )
        logger.info(
            "http_access",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": ms,
                "client": client,
            },
        )
        return response

    app.include_router(_router)
    return app


app = create_app()


def main() -> None:
    import uvicorn
    from tracker_core.custom_logger import configure_logging
    from tracker_core.internal.appctx.config import AppConfig

    configure_logging(AppConfig.log_level, debug=AppConfig.debug)
    with contextlib.suppress(KeyboardInterrupt):
        uvicorn.run(
            "ingest.osmand.api:app",
            host="0.0.0.0",
            port=8766,
            proxy_headers=True,
            forwarded_allow_ips="*",
            access_log=False,
            log_config=None,
        )


if __name__ == "__main__":
    main()
