"""Pure-function analytics over a list of positions.

Inputs are ordered chronologically. We avoid SQL geometry math so the same
helpers can be used in tests and the API. Distances use haversine.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from tracker_core.store.models import Position

EARTH_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon pairs, in kilometers."""
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = rlat2 - rlat1
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_KM * asin(sqrt(h))


@dataclass
class Trip:
    """Detected drive segment between two stops. Computed, not persisted."""

    started_at: datetime
    ended_at: datetime
    distance_km: float
    duration_s: int
    max_speed_kmh: float
    avg_speed_kmh: float
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    points: int


@dataclass
class OvernightStop:
    """A ≥ :data:`OVERNIGHT_MIN_S` stationary window spanning ~local 02:00."""

    started_at: datetime
    ended_at: datetime
    lon: float
    lat: float
    duration_s: int


# --- detection -------------------------------------------------------------

# A "stop" is a window of >= STOP_MIN_S where positions stay within STOP_RADIUS_M.
STOP_RADIUS_M = 80.0
STOP_MIN_S = 8 * 60  # 8 min: end of trip
OVERNIGHT_MIN_S = 4 * 3600  # 4h sitting still anywhere counts as overnight stop


def _segment_stops(positions: Sequence[Position]) -> list[tuple[int, int]]:
    """Return (start_idx, end_idx_inclusive) for stationary windows."""
    if len(positions) < 2:
        return []
    out: list[tuple[int, int]] = []
    i = 0
    n = len(positions)
    while i < n:
        j = i
        # extend while within radius of pivot
        while j + 1 < n:
            d_m = haversine_km(positions[i].lat, positions[i].lon, positions[j + 1].lat, positions[j + 1].lon) * 1000
            if d_m > STOP_RADIUS_M:
                break
            j += 1
        dur = (positions[j].time_id - positions[i].time_id).total_seconds()
        if dur >= STOP_MIN_S and j > i:
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def detect_trips(positions: Sequence[Position]) -> list[Trip]:
    """Split positions into trips separated by stops >= STOP_MIN_S."""
    if len(positions) < 2:
        return []
    stops = _segment_stops(positions)
    boundaries: list[tuple[int, int]] = []  # (trip_start, trip_end) inclusive on positions
    cursor = 0
    for s, e in stops:
        if s > cursor:
            boundaries.append((cursor, s))
        cursor = e
    if cursor < len(positions) - 1:
        boundaries.append((cursor, len(positions) - 1))

    trips: list[Trip] = []
    for a, b in boundaries:
        seg = positions[a : b + 1]
        if len(seg) < 2:
            continue
        dist_km = 0.0
        max_speed = 0.0
        for k in range(1, len(seg)):
            dist_km += haversine_km(seg[k - 1].lat, seg[k - 1].lon, seg[k].lat, seg[k].lon)
            if seg[k].speed and seg[k].speed > max_speed:
                max_speed = float(seg[k].speed)
        dur = (seg[-1].time_id - seg[0].time_id).total_seconds()
        avg = dist_km / (dur / 3600) if dur > 0 else 0.0
        # Don't emit micro trips
        if dist_km < 0.2:
            continue
        trips.append(
            Trip(
                started_at=seg[0].time_id,
                ended_at=seg[-1].time_id,
                distance_km=dist_km,
                duration_s=int(dur),
                max_speed_kmh=max_speed,
                avg_speed_kmh=avg,
                start_lon=seg[0].lon,
                start_lat=seg[0].lat,
                end_lon=seg[-1].lon,
                end_lat=seg[-1].lat,
                points=len(seg),
            ),
        )
    return trips


def detect_overnights(positions: Sequence[Position]) -> list[OvernightStop]:
    """Detect overnight stops in ``positions``.

    A stop window of >= :data:`OVERNIGHT_MIN_S` whose interval includes any
    local 02:00 counts as overnight. We approximate "local" via a longitude
    offset (1h per 15°) so we don't depend on a per-user timezone lookup.
    """
    stops = _segment_stops(positions)
    out: list[OvernightStop] = []
    for s, e in stops:
        a, b = positions[s], positions[e]
        dur = (b.time_id - a.time_id).total_seconds()
        if dur < OVERNIGHT_MIN_S:
            continue
        # rough local offset from longitude: 1h per 15deg
        lon = (a.lon + b.lon) / 2
        offset = timedelta(hours=lon / 15.0)
        local_start = a.time_id + offset
        local_end = b.time_id + offset
        # check if 02:00 of any day in [local_start, local_end] is inside
        cursor = local_start.replace(hour=2, minute=0, second=0, microsecond=0)
        if cursor < local_start:
            cursor += timedelta(days=1)
        if cursor <= local_end:
            mid_lat = sum(p.lat for p in positions[s : e + 1]) / (e - s + 1)
            mid_lon = sum(p.lon for p in positions[s : e + 1]) / (e - s + 1)
            out.append(
                OvernightStop(
                    started_at=a.time_id,
                    ended_at=b.time_id,
                    lon=mid_lon,
                    lat=mid_lat,
                    duration_s=int(dur),
                ),
            )
    return out


# --- mileage ---------------------------------------------------------------


def mileage_buckets(positions: Sequence[Position], granularity: str = "day") -> list[tuple[str, float]]:
    """Return (bucket_label, distance_km) tuples in chrono order.

    granularity: 'day' | 'month' | 'year'.
    """
    fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}.get(granularity, "%Y-%m-%d")
    bucket: dict[str, float] = {}
    if len(positions) < 2:
        return []
    for k in range(1, len(positions)):
        a, b = positions[k - 1], positions[k]
        d = haversine_km(a.lat, a.lon, b.lat, b.lon)
        # gap > 1h => probably not contiguous travel, skip
        if (b.time_id - a.time_id).total_seconds() > 3600:
            continue
        # speed sanity: > 250 km/h => GPS jump
        if d / max((b.time_id - a.time_id).total_seconds() / 3600, 1e-9) > 250:
            continue
        # attribute to end-time bucket
        ts_local = b.time_id.astimezone(UTC)
        key = ts_local.strftime(fmt)
        bucket[key] = bucket.get(key, 0.0) + d
    return sorted(bucket.items())


def trip_summary(positions: Sequence[Position]) -> dict:
    """Aggregate stats across the supplied window."""
    trips = detect_trips(positions)
    total_km = sum(t.distance_km for t in trips)
    total_s = sum(t.duration_s for t in trips)
    max_speed = max((t.max_speed_kmh for t in trips), default=0.0)
    overnights = detect_overnights(positions)
    return {
        "trips": len(trips),
        "distance_km": total_km,
        "duration_s": total_s,
        "max_speed_kmh": max_speed,
        "avg_speed_kmh": (total_km / (total_s / 3600)) if total_s > 0 else 0.0,
        "overnights": len(overnights),
        "points": len(positions),
    }


def to_gpx(
    positions: Iterable[Position], name: str = "track", include_metadata: bool = True
) -> Generator[str, None, None]:
    """Serialise positions to a GPX 1.1 ``<trk>`` document containing only location and time."""
    yield '<?xml version="1.0" encoding="UTF-8"?>\n'
    yield '<gpx version="1.1" creator="gps-tracker" xmlns="http://www.topografix.com/GPX/1/1">\n'
    yield f"<trk><name>{_xml_escape(name)}</name><trkseg>\n"
    for p in positions:
        t = p.time_id if p.time_id.tzinfo is not None else p.time_id.replace(tzinfo=UTC)
        time_str = t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        yield f'<trkpt lat="{p.lat}" lon="{p.lon}"><time>{time_str}</time></trkpt>\n'
    yield "</trkseg></trk></gpx>\n"


def to_csv(positions: Iterable[Position]) -> Generator[str, None, None]:
    """Serialise positions to RFC 4180-ish CSV. Trailing newline included."""
    yield "time_id,lat,lon,altitude,speed_kmh,satellites\n"
    for p in positions:
        t = p.time_id if p.time_id.tzinfo is not None else p.time_id.replace(tzinfo=UTC)
        yield (
            ",".join(
                [
                    t.astimezone(UTC).isoformat(),
                    f"{p.lat}",
                    f"{p.lon}",
                    "" if p.altitude is None else f"{p.altitude}",
                    "" if p.speed is None else f"{p.speed}",
                    "" if p.satellites is None else f"{p.satellites}",
                ],
            )
            + "\n"
        )


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
