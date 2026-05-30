"""Overnight spot detection and persistence service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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

    Full-window rescan: always scans the entire trip window (started_at →
    effective end). Reconciles detected stops against existing DB rows —
    updating counts, creating new spots, and deleting spots that are no longer
    within the trip window. Cooldown applies only to ongoing trips.
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

    # Closed trips: skip if marker already covers the latest position (window is fixed)
    if trip.ended_at is not None and marker is not None and latest_trip_position_time <= marker:
        return OvernightDetectResult(status="up_to_date", last_checked_position_time=marker)

    # Ongoing trips: cooldown to avoid expensive rescans on every open
    if (
        trip.ended_at is None
        and trip.overnights_detected_at is not None
        and marker is not None
        and latest_trip_position_time <= marker
        and (now - trip.overnights_detected_at).total_seconds() < analytics.OVERNIGHT_MIN_S
    ):
        return OvernightDetectResult(status="cooldown", last_checked_position_time=marker)

    # Full-window scan
    pts = await positions_in_window_capped(db, trip.device_id, trip.started_at, latest_trip_position_time)
    if not pts:
        return OvernightDetectResult(status="up_to_date", last_checked_position_time=marker)

    # Run detection on full window
    raw_overnights = analytics.detect_overnights(pts)
    merged = _merge_consecutive_overnights(raw_overnights)

    existing_spots = list((await db.scalars(select(OvernightSpot).where(OvernightSpot.trip_id == trip.id))).all())

    # Delete spots whose last_stay_at is now outside the trip window
    deleted_count = 0
    for spot in list(existing_spots):
        if spot.last_stay_at < trip.started_at or spot.last_stay_at > scan_end:
            await db.delete(spot)
            existing_spots.remove(spot)
            deleted_count += 1

    # Reconcile detected spots against surviving existing spots
    created_count = 0
    updated_count = 0
    matched: set[int] = set()
    next_name_idx = (
        max((int(s.name.split("#")[-1]) for s in existing_spots if s.name.startswith("Overnight #")), default=0) + 1
    )

    for lon, lat, nights, last_stay in merged:
        existing = _find_nearby_overnight_spot(existing_spots, lon, lat)
        if existing:
            matched.add(existing.id)
            if existing.nights_count != nights or existing.last_stay_at != last_stay:
                existing.nights_count = nights
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

    # Existing spots that had no detected match are stale — delete them
    for spot in existing_spots:
        if spot.id and spot.id not in matched:
            await db.delete(spot)
            deleted_count += 1

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


def _count_nights(o: analytics.OvernightStop) -> int:
    offset = timedelta(hours=o.lon / 15.0)
    local_start = o.started_at + offset
    local_end = o.ended_at + offset
    cursor = local_start.replace(hour=2, minute=0, second=0, microsecond=0)
    if cursor < local_start:
        cursor += timedelta(days=1)
    nights = 0
    while cursor <= local_end:
        nights += 1
        cursor += timedelta(days=1)
    return max(1, nights)


def _merge_consecutive_overnights(
    overnights: list[analytics.OvernightStop],
) -> list[tuple[float, float, int, datetime]]:
    """Merge consecutive nights at same location. Returns [(lon, lat, nights, last_stay_at)]."""
    if not overnights:
        return []

    merged: list[tuple[float, float, int, datetime, datetime]] = []

    for o in overnights:
        o_nights = _count_nights(o)
        # Check if this overnight is at same location as previous (within 80m)
        if merged:
            prev_lon, prev_lat, prev_nights, prev_start, prev_end = merged[-1]
            dist_m = analytics.haversine_km(prev_lat, prev_lon, o.lat, o.lon) * 1000

            # If within 80m AND consecutive (gap < 24h), merge
            gap_hours = (o.started_at - prev_end).total_seconds() / 3600
            if dist_m <= 80 and gap_hours < 24:
                # Update last entry: average coords, increment nights, update end time
                new_nights = prev_nights + o_nights
                avg_lon = (prev_lon * prev_nights + o.lon * o_nights) / new_nights
                avg_lat = (prev_lat * prev_nights + o.lat * o_nights) / new_nights
                merged[-1] = (avg_lon, avg_lat, new_nights, prev_start, o.ended_at)
                continue

        # New location
        merged.append((o.lon, o.lat, o_nights, o.started_at, o.ended_at))

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
