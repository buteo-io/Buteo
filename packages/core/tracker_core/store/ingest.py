"""Shared persistence helpers for GPS ingest.

Both the OsmAnd HTTP ingest and the Codec8 TCP ingest parse incoming data into
:class:`PositionData` objects and then call :func:`store_positions` to persist
them.  Neither parser needs to know about the ORM schema.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker_core.store.models import Device, Position

logger = logging.getLogger(__name__)

# Spike filter constants (strict isolated-spike rule)
MAX_NEIGHBOR_GAP_S = 900  # 15 minutes
SPIKE_LEG_MIN_M = 10_000  # 10 km minimum for each leg
RETURN_NEAR_MAX_M = 1_500  # 1.5 km max for A-C distance
EARTH_KM = 6371.0088


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers."""
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = rlat2 - rlat1
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_KM * asin(sqrt(h))


def _to_utc(dt: datetime) -> datetime:
    """Normalize datetime to UTC, handling naive datetimes from SQLite."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_isolated_spike(a: PositionData, b: PositionData, c: PositionData, device_id: int | None = None) -> bool:
    """Check if middle point B is an isolated spike (A->B->C out-and-back).

    Drop B only if:
    - Both gaps short (<=15 min)
    - Both legs far (>=10 km)
    - A and C close again (<=1.5 km)
    """
    a_utc = _to_utc(a.time_id)
    b_utc = _to_utc(b.time_id)
    c_utc = _to_utc(c.time_id)

    dt_ab = (b_utc - a_utc).total_seconds()
    dt_bc = (c_utc - b_utc).total_seconds()

    if dt_ab <= 0 or dt_bc <= 0:
        return False

    if dt_ab > MAX_NEIGHBOR_GAP_S or dt_bc > MAX_NEIGHBOR_GAP_S:
        return False

    dist_ab = _haversine_km(a.lat, a.lon, b.lat, b.lon) * 1000
    dist_bc = _haversine_km(b.lat, b.lon, c.lat, c.lon) * 1000
    dist_ac = _haversine_km(a.lat, a.lon, c.lat, c.lon) * 1000

    if dist_ab < SPIKE_LEG_MIN_M or dist_bc < SPIKE_LEG_MIN_M:
        return False

    if dist_ac > RETURN_NEAR_MAX_M:
        return False

    logger.info(
        "spike_filtered",
        extra={
            "device_id": device_id,
            "b_time": b.time_id.isoformat(),
            "dist_ab_m": round(dist_ab),
            "dist_bc_m": round(dist_bc),
            "dist_ac_m": round(dist_ac),
        },
    )
    return True


@dataclass
class PositionData:
    """Protocol-agnostic representation of a single GPS fix."""

    time_id: datetime
    lat: float
    lon: float
    altitude: float | None = None
    speed: float | None = None  # km/h
    satellites: int | None = None


async def store_positions(
    db: AsyncSession,
    device_id: int,
    fixes: list[PositionData],
) -> int:
    """Persist *fixes* and update :attr:`Device.last_seen_at`.

    Applies isolated spike filter: removes middle point B from A->B->C pattern
    when both legs are far (>=10km) but A and C are close again (<=1.5km),
    with short gaps (<=15min) on both sides.

    Returns the number of rows written.  Caller is responsible for opening
    the session; this function commits it.
    """
    if not fixes:
        return 0

    # Sort incoming fixes by time
    sorted_fixes = sorted(fixes, key=lambda f: f.time_id)

    # Query last 2 persisted non-filtered positions for spike detection with lookback
    prev_positions = (
        await db.scalars(
            select(Position)
            .where(Position.device_id == device_id, Position.is_filtered.is_(False))
            .order_by(Position.time_id.desc())
            .limit(2),
        )
    ).all()
    # Reverse to get chronological order (oldest first)
    prev_positions = list(reversed(prev_positions))

    # Convert prev_positions to PositionData style for the rolling window
    prev_data = [
        PositionData(
            time_id=p.time_id,
            lat=p.lat,
            lon=p.lon,
            altitude=p.altitude,
            speed=p.speed,
            satellites=p.satellites,
        )
        for p in prev_positions
    ]

    # Build rolling window: [prev1, prev2, new1, new2, ...]
    window: list[PositionData] = prev_data + sorted_fixes

    # Track positions to mark as filtered
    skip_indices: set[int] = set()
    delete_ids: list[int] = []

    # Check each potential middle point (skip first two which are lookback)
    for i in range(2, len(window)):
        a = window[i - 2]
        b = window[i - 1]
        c = window[i]

        if _is_isolated_spike(a, b, c, device_id):
            b_index = i - 1
            if b_index < len(prev_positions):
                # b is a persisted position - mark for update to is_filtered = True
                delete_ids.append(prev_positions[b_index].id)
                skip_indices.add(b_index)
            else:
                # b is in the new batch - skip adding it (actually, we will add it with is_filtered=True)
                skip_indices.add(b_index)

    # Build Position rows, setting is_filtered to True for spikes
    rows = []
    first_valid_idx = len(prev_positions)
    for i, fix in enumerate(sorted_fixes):
        actual_index = first_valid_idx + i
        is_f = actual_index in skip_indices
        rows.append(
            Position(
                device_id=device_id,
                time_id=fix.time_id,
                lat=fix.lat,
                lon=fix.lon,
                altitude=fix.altitude,
                speed=fix.speed,
                satellites=fix.satellites,
                is_filtered=is_f,
            ),
        )

    # Add new positions first
    if rows:
        db.add_all(rows)

    # Mark persisted spike positions as filtered
    for pos_id in delete_ids:
        pos = await db.get(Position, pos_id)
        if pos:
            pos.is_filtered = True

    # Update last_seen_at to latest valid position
    valid_rows = [row for row in rows if not row.is_filtered]
    last_ts = max(row.time_id for row in valid_rows) if valid_rows else max(fix.time_id for fix in fixes)

    device = await db.get(Device, device_id)
    if device:
        device.last_seen_at = last_ts

    await db.commit()
    return len(valid_rows)
