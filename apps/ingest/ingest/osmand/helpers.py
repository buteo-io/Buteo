"""Parsing and persistence helpers for the OsmAnd HTTP ingest."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.store.ingest import PositionData, store_positions
from tracker_core.store.models import Device
from tracker_core.store.tenant_db_manager import get_tenant_by_imei, tenant_db_manager

logger = logging.getLogger(__name__)
# 1 knot = 1.852 km/h. OsmAnd protocol transmits speed in knots; we store km/h.
_KNOTS_TO_KMH = 1.852

# Sanity bounds on inbound timestamps. A misconfigured client posting `0`
# would otherwise drop a 1970-01-01 row in the DB and break charts; a
# clock-skewed phone posting "next year" pollutes the live view. We pin the
# floor at 2020-01-01 (this project did not exist before then) and the
# ceiling at "one day in the future" to absorb minor clock drift.
_MIN_TS = datetime(2020, 1, 1, tzinfo=timezone.utc)
_FUTURE_SLACK = timedelta(days=1)


def _flt(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _parse_timestamp(raw: str | None) -> datetime:
    """Accept unix seconds (int/float) or ISO 8601. Fall back to now().

    Enforces a sanity window of ``[2020-01-01, now + 1 day]``. Anything
    outside that range is rejected as 400 — a phone with a busted clock
    posting 1970 or 2099 would otherwise corrupt the live view forever.
    """
    if not raw:
        return datetime.now(tz=timezone.utc)
    # Numeric: unix seconds (some clients also send millis — heuristic split).
    ts: datetime | None = None
    try:
        n = float(raw)
        if n > 1e12:  # millis since epoch
            n /= 1000.0
        ts = datetime.fromtimestamp(n, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    if ts is None:
        # ISO 8601 — accept trailing Z too.
        iso = raw.replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(iso)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad timestamp") from e
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    upper = datetime.now(tz=timezone.utc) + _FUTURE_SLACK
    if ts < _MIN_TS or ts > upper:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "timestamp out of range (check device clock)",
        )
    return ts


def _set_param(merged: dict[str, str], key: str, value: object | None) -> None:
    if value is not None:
        merged.setdefault(key, str(value))


def _str(raw: object | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float)):
        return str(raw)
    return None


def _merge_json_payload(merged: dict[str, str], payload: object) -> None:
    if not isinstance(payload, dict):
        return

    location = payload.get("location")
    if not isinstance(location, dict):
        return

    coords = location.get("coords")
    if not isinstance(coords, dict):
        return

    compat_qs = location.get("_")
    if compat_qs is None:
        compat_qs = payload.get("_")
    if isinstance(compat_qs, str) and compat_qs:
        merged.update(
            {
                k: v
                for k, v in parse_qsl(compat_qs.lstrip("?"), keep_blank_values=True)
                if v != ""
            }
        )

    ident = payload.get("id") or payload.get("device_id") or payload.get("deviceid")
    _set_param(merged, "id", ident)

    _set_param(merged, "lat", coords.get("latitude"))
    _set_param(merged, "lon", coords.get("longitude"))
    _set_param(merged, "speed", coords.get("speed"))
    _set_param(merged, "heading", coords.get("heading"))
    _set_param(merged, "altitude", coords.get("altitude"))
    _set_param(merged, "timestamp", location.get("timestamp") or location.get("time"))


async def _params(request: Request) -> dict[str, str]:
    """Merge query string + form body. Query wins on duplicate keys.

    iOS Traccar Client sends ``POST /?id=...&lat=...`` with empty body; OsmAnd
    Android sends form-encoded body. Supporting both is one line.
    """
    merged: dict[str, str] = {}
    if request.method == "POST":
        ctype = request.headers.get("content-type", "")
        if ctype.startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")
        ):
            try:
                form = await request.form()
            except Exception:
                form = {}
            merged.update({k: v for k, v in form.items() if isinstance(v, str)})
        elif ctype.startswith("application/json"):
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            _merge_json_payload(merged, payload)
    merged.update(dict(request.query_params.multi_items()))
    return merged


def _owntracks_topic_device(topic: str | None) -> str | None:
    if not topic:
        return None
    parts = topic.split("/")
    if len(parts) < 3:
        return None
    return parts[-1] or None


def _owntracks_ident(request: Request, payload: dict[str, object]) -> str | None:
    return (
        request.query_params.get("id")
        or request.headers.get("x-limit-d")
        or request.query_params.get("d")
        or _str(payload.get("id"))
        or _str(payload.get("deviceid"))
        or _str(payload.get("device_id"))
        or _owntracks_topic_device(_str(payload.get("topic")))
        or _str(payload.get("tid"))
    )


def _parse_owntracks_fix(
    request: Request, payload: object
) -> tuple[str, PositionData] | None:
    if not isinstance(payload, dict):
        logger.warning("owntracks_bad_type", extra={"type": type(payload).__name__})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad owntracks payload")

    msg_type = _str(payload.get("_type"))
    if msg_type == "encrypted":
        logger.warning("owntracks_encrypted_unsupported")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "encrypted owntracks payload unsupported"
        )
    if msg_type != "location":
        return None

    ident = _owntracks_ident(request, payload)
    if not ident:
        logger.warning("owntracks_missing_device_id", extra={"payload": payload})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing device id")

    lat = _flt(_str(payload.get("lat")))
    lon = _flt(_str(payload.get("lon")))
    if lat is None or lon is None:
        logger.warning("owntracks_missing_coords", extra={"payload": payload})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing lat/lon")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        logger.warning("owntracks_invalid_coords", extra={"lat": lat, "lon": lon})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "lat/lon out of range")

    raw_ts = payload.get("tst")
    if raw_ts is None:
        raw_ts = payload.get("created_at")

    try:
        ts = _parse_timestamp(_str(raw_ts))
    except HTTPException as e:
        logger.warning(
            "owntracks_bad_timestamp", extra={"raw_ts": raw_ts, "error": str(e.detail)}
        )
        raise

    speed_kmh = _flt(_str(payload.get("vel")))
    if speed_kmh is not None and speed_kmh < 0:
        speed_kmh = 0

    altitude = _flt(_str(payload.get("alt")))
    satellites = _int(
        _str(payload.get("sat") or payload.get("sats") or payload.get("satellites"))
    )

    return ident, PositionData(
        time_id=ts,
        lat=lat,
        lon=lon,
        altitude=altitude,
        speed=speed_kmh,
        satellites=satellites,
    )


async def _resolve_device(db: AsyncSession, ident: str) -> Device:
    d = await db.scalar(select(Device).where(Device.imei == ident))
    if d is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown device")
    if d.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, "device revoked")
    return d


def _parse_fix(p: dict[str, str]) -> tuple[str, PositionData]:
    """Parse OsmAnd params into (ident, PositionData). Raises HTTPException on bad input."""
    logger.debug("ingest raw params: %s", p)
    ident = p.get("id") or p.get("deviceid") or p.get("device_id")
    if not ident:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing id")

    lat = _flt(p.get("lat") or p.get("latitude"))
    lon = _flt(p.get("lon") or p.get("longitude") or p.get("lng"))
    if lat is None or lon is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing lat/lon")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "lat/lon out of range")

    ts = _parse_timestamp(p.get("timestamp") or p.get("time"))
    logger.info("ingest parsed ts: %s (tzinfo=%s)", ts, ts.tzinfo)

    speed_kn = _flt(p.get("speed"))
    speed_kmh = speed_kn * _KNOTS_TO_KMH if speed_kn is not None else None
    if speed_kmh is not None and speed_kmh < 0:
        speed_kmh = 0
    altitude = _flt(p.get("altitude") or p.get("alt"))
    satellites = _int(p.get("sat") or p.get("sats") or p.get("satellites"))

    return ident, PositionData(
        time_id=ts,
        lat=lat,
        lon=lon,
        altitude=altitude,
        speed=speed_kmh,
        satellites=satellites,
    )


async def _ingest_one(p: dict[str, str]) -> None:
    ident, fix = _parse_fix(p)
    tenant_id = await get_tenant_by_imei(ident)
    if not tenant_id:
        logger.warning("traccar_unauthorized_tenant", extra={"ident": ident})
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "unknown or inactive device/tenant"
        )

    async with tenant_db_manager.get_tenant_session(tenant_id) as db:
        device = await _resolve_device(db, ident)
        written = await store_positions(db, device.id, [fix])
        logger.debug(
            "traccar_stored",
            extra={
                "device_id": device.id,
                "ident": ident,
                "lat": fix.lat,
                "lon": fix.lon,
                "time_id": fix.time_id.isoformat(),
                "written": written,
            },
        )


async def _ingest_one_owntracks(request: Request) -> bool:
    body = await request.body()
    if not body:
        logger.warning("owntracks_ignored", extra={"reason": "empty_body"})
        return False

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.warning("owntracks_bad_payload", extra={"error": str(e)})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad owntracks payload") from e

    parsed = _parse_owntracks_fix(request, payload)
    if parsed is None:
        msg_type = payload.get("_type") if isinstance(payload, dict) else None
        logger.info(
            "owntracks_ignored",
            extra={
                "reason": "non_location_payload"
                if msg_type != "location"
                else "unknown",
                "msg_type": msg_type,
            },
        )
        return False

    ident, fix = parsed
    tenant_id = await get_tenant_by_imei(ident)
    if not tenant_id:
        logger.warning("owntracks_unauthorized_tenant", extra={"ident": ident})
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "unknown or inactive device/tenant"
        )

    async with tenant_db_manager.get_tenant_session(tenant_id) as db:
        device = await _resolve_device(db, ident)
        written = await store_positions(db, device.id, [fix])
        logger.debug(
            "owntracks_stored",
            extra={
                "device_id": device.id,
                "ident": ident,
                "lat": fix.lat,
                "lon": fix.lon,
                "time_id": fix.time_id.isoformat(),
                "written": written,
            },
        )
    return True
