"""Analytics endpoints: trips, overnights, mileage, summary, exports."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core import analytics
from tracker_core.queries import positions_in_window_capped
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import User

from ..deps import current_user, get_db, own_device

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_dict(obj):
    return asdict(obj) if is_dataclass(obj) else dict(obj.__dict__)


# Allow only printable ASCII letters/digits/dash/underscore/dot/space in the
# fallback `filename=` token; everything else (CR/LF, quotes, semicolons,
# non-ASCII) goes through the percent-encoded `filename*=` per RFC 5987.
# Without this, a device name like `Camper "01"\r\nX-Inject: hi` would let
# the user inject arbitrary response headers (Content-Disposition is a
# user-controlled string today since `tracker_core.cli.manage --name` accepts anything).
_FILENAME_ASCII_SAFE = re.compile(r"[^A-Za-z0-9._\- ]+")


def _attach(name: str, fmt: str) -> dict:
    """Build a header-safe ``Content-Disposition`` for a download.

    Two parameters per RFC 6266 / RFC 5987:
        filename=  ASCII-safe fallback for legacy clients
        filename*= UTF-8 percent-encoded copy for modern clients
    """
    cleaned_name = re.sub(r"\s+", "_", name)
    raw = f"{cleaned_name}.{fmt}"
    ascii_fallback = _FILENAME_ASCII_SAFE.sub("_", raw).strip() or f"export.{fmt}"
    encoded = quote(raw, safe="")
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"
        ),
    }


@router.get("/devices/{device_id}/trips")
async def trips(
    device_id: PrefixUUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect trip segments across ``device_id`` within ``[from, to]``."""
    d = await own_device(db, user, device_id)
    pts = await positions_in_window_capped(db, d.id, from_, to)
    result = [_to_dict(t) for t in analytics.detect_trips(pts)]
    logger.debug(
        "analytics_trips user_id=%s device_id=%s count=%d",
        user.id,
        device_id,
        len(result),
    )
    return result


@router.get("/devices/{device_id}/overnights")
async def overnights(
    device_id: PrefixUUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect overnight stays within the window.

    Local-time is approximated from longitude; there is no per-user tz.
    """
    d = await own_device(db, user, device_id)
    pts = await positions_in_window_capped(db, d.id, from_, to)
    result = [_to_dict(o) for o in analytics.detect_overnights(pts)]
    logger.debug(
        "analytics_overnights user_id=%s device_id=%s count=%d",
        user.id,
        device_id,
        len(result),
    )
    return result


@router.get("/devices/{device_id}/summary")
async def summary(
    device_id: PrefixUUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate trip + overnight + mileage stats for the window."""
    d = await own_device(db, user, device_id)
    pts = await positions_in_window_capped(db, d.id, from_, to)
    logger.debug(
        "analytics_summary user_id=%s device_id=%s points=%d",
        user.id,
        device_id,
        len(pts),
    )
    return analytics.trip_summary(pts)


_DEFAULT_MILEAGE_DELTA = {
    "day": timedelta(days=30),
    "month": timedelta(days=365),
    "year": timedelta(days=365 * 5),
}


@router.get("/devices/{device_id}/mileage")
async def mileage(
    device_id: PrefixUUID,
    granularity: str = Query(default="day", pattern="^(day|month|year)$"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bucketed distance driven, defaulting the window per granularity."""
    d = await own_device(db, user, device_id)
    if not to:
        to = datetime.now(tz=timezone.utc)
    if not from_:
        from_ = to - _DEFAULT_MILEAGE_DELTA[granularity]
    pts = await positions_in_window_capped(db, d.id, from_, to)
    buckets = analytics.mileage_buckets(pts, granularity)
    logger.debug(
        "analytics_mileage user_id=%s device_id=%s granularity=%s buckets=%d",
        user.id,
        device_id,
        granularity,
        len(buckets),
    )
    return {
        "granularity": granularity,
        "total_km": sum(v for _, v in buckets),
        "buckets": [{"label": k, "km": v} for k, v in buckets],
    }


@router.get("/devices/{device_id}/export.gpx")
async def export_gpx(
    device_id: PrefixUUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serialise the window's positions as a GPX attachment."""
    d = await own_device(db, user, device_id)
    pts = await positions_in_window_capped(db, d.id, from_, to)
    logger.info(
        "export_gpx user_id=%s device_id=%s points=%d", user.id, device_id, len(pts)
    )
    return StreamingResponse(
        analytics.to_gpx(pts, name=d.name),
        media_type="application/gpx+xml",
        headers=_attach(d.name, "gpx"),
    )


@router.get("/devices/{device_id}/export.csv")
async def export_csv(
    device_id: PrefixUUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serialise the window's positions as a CSV attachment."""
    d = await own_device(db, user, device_id)
    pts = await positions_in_window_capped(db, d.id, from_, to)
    logger.info(
        "export_csv user_id=%s device_id=%s points=%d", user.id, device_id, len(pts)
    )
    return StreamingResponse(
        analytics.to_csv(pts),
        media_type="text/csv",
        headers=_attach(d.name, "csv"),
    )
