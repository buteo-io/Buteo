"""Overnight spot detection and persistence service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tracker_core.store.models import OvernightSpot, Position, Trip, User

from . import analytics
from .queries import positions_in_window_capped

logger = logging.getLogger(__name__)


@dataclass
class OvernightDetectResult:
    status: str
    created: int = 0
    updated: int = 0
    last_checked_position_time: datetime | None = None


async def detect_and_persist_overnights(
    db: AsyncSession,
    trip: Trip,
    user: User,
) -> OvernightDetectResult:
    """Detect overnight stops and persist as OvernightSpot records.

    Incremental and idempotent: scans only data after
    ``trip.overnights_last_checked_position_time`` and throttles reruns for
    ongoing trips to ``analytics.OVERNIGHT_MIN_S``.
    """
    now = datetime.now(tz=timezone.utc)
    scan_end = trip.ended_at if trip.ended_at is not None else now
    latest_trip_position_time = await db.scalar(
        select(func.max(Position.time_id)).where(
            Position.device_id == trip.device_id,
            Position.is_filtered.is_(False),
            Position.time_id >= trip.started_at,
            Position.time_id <= scan_end,
        ),
    )
    if latest_trip_position_time is None:
        return OvernightDetectResult(status="up_to_date")

    marker = trip.overnights_last_checked_position_time
    if marker is not None and latest_trip_position_time <= marker:
        return OvernightDetectResult(status="up_to_date", last_checked_position_time=marker)

    if (
        trip.ended_at is None
        and trip.overnights_detected_at is not None
        and (now - trip.overnights_detected_at).total_seconds() < analytics.OVERNIGHT_MIN_S
    ):
        return OvernightDetectResult(status="cooldown", last_checked_position_time=marker)

    scan_from = marker if marker is not None else trip.started_at
    pts = await positions_in_window_capped(db, trip.device_id, scan_from, latest_trip_position_time)
    if not pts:
        return OvernightDetectResult(status="up_to_date", last_checked_position_time=marker)

    # Run detection
    raw_overnights = analytics.detect_overnights(pts)

    # Merge consecutive nights at same location
    merged = _merge_consecutive_overnights(raw_overnights)

    existing_spots = list((await db.scalars(select(OvernightSpot).where(OvernightSpot.trip_id == trip.id))).all())

    # Create/update OvernightSpot entries
    created_count = 0
    updated_count = 0
    next_name_idx = len(existing_spots) + 1
    for lon, lat, nights, last_stay in merged:
        existing = _find_nearby_overnight_spot(existing_spots, lon, lat)
        if existing:
            new_nights = existing.nights_count + nights
            if existing.nights_count != new_nights or existing.last_stay_at != last_stay:
                existing.nights_count = new_nights
                existing.last_stay_at = last_stay
                updated_count += 1
        else:
            spot = OvernightSpot(
                user_id=user.id,
                trip_id=trip.id,
                name=f"Overnight #{next_name_idx}",
                lon=lon,
                lat=lat,
                nights_count=nights,
                last_stay_at=last_stay,
            )
            db.add(spot)
            existing_spots.append(spot)
            created_count += 1
            next_name_idx += 1

    marker_filter = (
        Trip.overnights_last_checked_position_time.is_(None)
        if marker is None
        else Trip.overnights_last_checked_position_time == marker
    )
    marker_update = await db.execute(
        update(Trip)
        .where(Trip.id == trip.id)
        .where(marker_filter)
        .values(
            overnights_detected_at=now,
            overnights_last_checked_position_time=latest_trip_position_time,
        ),
    )
    if marker_update.rowcount != 1:
        await db.rollback()
        return OvernightDetectResult(status="race_lost", last_checked_position_time=marker)

    await db.commit()

    return OvernightDetectResult(
        status="updated",
        created=created_count,
        updated=updated_count,
        last_checked_position_time=latest_trip_position_time,
    )


def _merge_consecutive_overnights(
    overnights: list[analytics.OvernightStop],
) -> list[tuple[float, float, int, datetime]]:
    """Merge consecutive nights at same location. Returns [(lon, lat, nights, last_stay_at)]."""
    if not overnights:
        return []

    merged: list[tuple[float, float, int, datetime, datetime]] = []

    for o in overnights:
        # Check if this overnight is at same location as previous (within 80m)
        if merged:
            prev_lon, prev_lat, prev_nights, prev_start, prev_end = merged[-1]
            dist_m = analytics.haversine_km(prev_lat, prev_lon, o.lat, o.lon) * 1000

            # If within 80m AND consecutive (gap < 24h), merge
            gap_hours = (o.started_at - prev_end).total_seconds() / 3600
            if dist_m <= 80 and gap_hours < 24:
                # Update last entry: average coords, increment nights, update end time
                avg_lon = (prev_lon * prev_nights + o.lon) / (prev_nights + 1)
                avg_lat = (prev_lat * prev_nights + o.lat) / (prev_nights + 1)
                merged[-1] = (avg_lon, avg_lat, prev_nights + 1, prev_start, o.ended_at)
                continue

        # New location
        merged.append((o.lon, o.lat, 1, o.started_at, o.ended_at))

    return [(lon, lat, nights, ended_at) for lon, lat, nights, _, ended_at in merged]


def _find_nearby_overnight_spot(
    spots: list[OvernightSpot],
    lon: float,
    lat: float,
) -> OvernightSpot | None:
    """Find existing overnight spot within 80m in this trip."""
    for s in spots:
        dist_m = analytics.haversine_km(s.lat, s.lon, lat, lon) * 1000
        if dist_m <= 80:
            return s
    return None
