"""User-created trips. Owner derived through device.user_id."""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core import analytics
from tracker_core.features import Feature
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.queries import positions_in_window_capped
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import Device, Entity, OvernightSpot, Place, Trip, User
from tracker_core.store.models import place_trips as place_trips_t

from ..deps import current_user, get_db, own_device, own_trip, require_feature
from ..schemas import PositionOut, UTCModel
from .analytics import _attach
from .places import PlaceOut
from .places import _out as _place_out

logger = logging.getLogger(__name__)

router = APIRouter()


class TripIn(BaseModel):
    device_id: PrefixUUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    started_at: datetime
    # ``None`` => ongoing. Effective end is "now" until the trip is closed.
    ended_at: datetime | None = None


class TripUpdateIn(BaseModel):
    """Partial update for ``PATCH /trips/{id}``.

    Every field is optional; only the keys actually present in the JSON
    body are touched. ``ended_at`` is tri-state by design: a missing key
    leaves the trip alone, an explicit ``null`` reopens an ended trip, an
    explicit timestamp closes it.
    """

    model_config = {"extra": "forbid"}

    device_id: PrefixUUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class TripOut(UTCModel):
    id: PrefixUUID
    device_id: PrefixUUID
    name: str
    description: str | None
    started_at: datetime
    ended_at: datetime | None


class TripStats(BaseModel):
    distance_km: float
    duration_s: int
    moving_s: int
    max_speed_kmh: float
    avg_speed_kmh: float
    moving_avg_speed_kmh: float
    overnights: int
    points: int


def _out(t: Trip, device_pid: PrefixUUID) -> TripOut:
    return TripOut(
        id=t.public_id,
        device_id=device_pid,
        name=t.name,
        description=t.description,
        started_at=t.started_at,
        ended_at=t.ended_at,
    )


def _check_window(started_at: datetime, ended_at: datetime | None) -> None:
    if ended_at is not None and ended_at <= started_at:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "ended_at must be after started_at"
        )


def _effective_end(t: Trip) -> datetime:
    """Upper bound for stats / positions queries. NOW for ongoing trips."""
    if t.ended_at is not None:
        return t.ended_at
    now = datetime.now(tz=timezone.utc)
    return now if t.started_at.tzinfo is not None else now.replace(tzinfo=None)


async def _commit_or_409_ongoing(db: AsyncSession) -> None:
    """Commit; map the partial-unique violation to 409 (already ongoing)."""
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if "ux_trips_one_ongoing_per_device" in str(
            e.orig
        ) or "UNIQUE constraint failed: trips.device_id" in str(e.orig):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Device already has an ongoing trip. End it before starting another.",
            ) from e
        raise


@router.get("/trips", response_model=list[TripOut])
async def list_trips(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return every trip across all devices owned by the caller, newest first."""
    stmt = (
        select(Trip, Device.public_id)
        .join(Device, Device.id == Trip.device_id)
        .join(Entity, Entity.id == Device.entity_id)
        .where(Entity.user_id == user.id)
    )
    stmt = stmt.order_by(Trip.started_at.desc())
    rows = (await db.execute(stmt)).all()
    logger.debug("list_trips user_id=%s count=%d", user.id, len(rows))
    return [_out(t, dpid) for t, dpid in rows]


@router.post("/trips", response_model=TripOut)
async def create_trip(
    body: TripIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_feature(Feature.CAN_WRITE)),
):
    """Create a new trip on one of the caller's devices.

    Errors:
        404: ``device_id`` is unknown or owned by somebody else.
        400: ``ended_at`` is not after ``started_at``.
    """
    d = await own_device(db, user, body.device_id)
    _check_window(body.started_at, body.ended_at)
    t = Trip(
        device_id=d.id,
        name=body.name,
        description=body.description,
        started_at=body.started_at,
        ended_at=body.ended_at,
    )
    db.add(t)
    await _commit_or_409_ongoing(db)
    await db.refresh(t)
    logger.info(
        "trip_create user_id=%s trip_id=%s name=%r", user.id, t.public_id, body.name
    )
    return _out(t, d.public_id)


@router.patch("/trips/{trip_id}", response_model=TripOut)
async def update_trip(
    trip_id: PrefixUUID,
    body: TripUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_feature(Feature.CAN_WRITE)),
):
    """Partial update of a trip. Only the fields present in the body change.

    Use cases this enables in one call: rename, edit description, move to
    a different device, extend the window, close (set ``ended_at``), or
    reopen (set ``ended_at: null``).
    """
    t, current_device = await own_trip(db, user, trip_id)
    # `model_fields_set` lets us tell missing-key vs explicit-null apart —
    # important for `ended_at: null` (reopen) vs absent (leave as-is).
    fields = body.model_fields_set
    target_device = current_device
    if "device_id" in fields:
        if body.device_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "device_id cannot be null")
        target_device = await own_device(db, user, body.device_id)
        t.device_id = target_device.id
    new_started = body.started_at if "started_at" in fields else t.started_at
    new_ended = body.ended_at if "ended_at" in fields else t.ended_at
    _check_window(new_started, new_ended)
    if "name" in fields:
        if body.name is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "name cannot be null")
        t.name = body.name
    if "description" in fields:
        t.description = body.description
    if "started_at" in fields:
        t.started_at = new_started
    if "ended_at" in fields:
        t.ended_at = new_ended
    if "started_at" in fields or "ended_at" in fields:
        t.overnights_last_checked_position_time = None
    await _commit_or_409_ongoing(db)
    await db.refresh(t)
    logger.info(
        "trip_update user_id=%s trip_id=%s fields=%s",
        user.id,
        t.public_id,
        sorted(fields),
    )
    return _out(t, target_device.public_id)


class TripEndIn(BaseModel):
    # Optional explicit end timestamp; defaults to "now" when omitted.
    ended_at: datetime | None = None


@router.post("/trips/{trip_id}/end", response_model=TripOut)
async def end_trip(
    trip_id: PrefixUUID,
    body: TripEndIn | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_feature(Feature.CAN_WRITE)),
):
    """Close an ongoing trip by setting ``ended_at``.

    Idempotent on already-closed trips: returns the current state. Validates
    that the chosen end is strictly after ``started_at``.
    """
    t, d = await own_trip(db, user, trip_id)
    if t.ended_at is not None:
        return _out(t, d.public_id)
    end = (body.ended_at if body else None) or datetime.now(tz=timezone.utc)
    if t.started_at.tzinfo is None and end.tzinfo is not None:
        end = end.replace(tzinfo=None)
    elif t.started_at.tzinfo is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= t.started_at:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ended_at must be after started_at",
        )
    t.ended_at = end
    await db.commit()
    await db.refresh(t)
    logger.info("trip_end user_id=%s trip_id=%s", user.id, trip_id)
    return _out(t, d.public_id)


@router.delete("/trips/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_feature(Feature.CAN_WRITE)),
):
    """Delete a trip. 204 on success, 404 if not owned."""
    t, _ = await own_trip(db, user, trip_id)
    spots_stmt = await db.execute(
        select(OvernightSpot).where(OvernightSpot.trip_id == t.id)
    )
    spots = spots_stmt.scalars().all()
    data_dir = AppConfig.data_dir or "/data"
    for spot in spots:
        media_dir = Path(data_dir) / "uploads" / str(spot.user_id) / str(spot.public_id)
        if media_dir.exists() and media_dir.is_dir():
            try:
                shutil.rmtree(media_dir)
                logger.info(
                    "trip_delete_media_dir user_id=%s spot_id=%s path=%s",
                    user.id,
                    spot.public_id,
                    media_dir,
                )
            except Exception as e:
                logger.error(
                    "trip_delete_media_dir_failed user_id=%s spot_id=%s path=%s error=%s",
                    user.id,
                    spot.public_id,
                    media_dir,
                    e,
                )
    await db.delete(t)
    await db.commit()
    logger.info("trip_delete user_id=%s trip_id=%s", user.id, trip_id)


@router.get("/trips/{trip_id}/stats", response_model=TripStats)
async def trip_stats(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute stats (distance, moving time, speed, overnights) for a trip window.

    For ongoing trips (``ended_at IS NULL``) the upper bound is "now".
    """
    t, _ = await own_trip(db, user, trip_id)
    end = _effective_end(t)
    pts = await positions_in_window_capped(db, t.device_id, t.started_at, end)
    distance = 0.0
    moving_s = 0
    max_speed = 0.0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        distance += analytics.haversine_km(a.lat, a.lon, b.lat, b.lon)
        if b.speed and b.speed > max_speed:
            max_speed = float(b.speed)
        dt = (b.time_id - a.time_id).total_seconds()
        if 0 < dt < 3600 and (b.speed or 0) > 3:
            moving_s += int(dt)
    duration = int((end - t.started_at).total_seconds())
    logger.debug(
        "trip_stats user_id=%s trip_id=%s points=%d", user.id, trip_id, len(pts)
    )
    return TripStats(
        distance_km=distance,
        duration_s=duration,
        moving_s=moving_s,
        max_speed_kmh=max_speed,
        avg_speed_kmh=distance / (duration / 3600) if duration > 0 else 0.0,
        moving_avg_speed_kmh=distance / (moving_s / 3600) if moving_s > 0 else 0.0,
        overnights=len(analytics.detect_overnights(pts)),
        points=len(pts),
    )


@router.get("/trips/{trip_id}/positions", response_model=list[PositionOut])
async def trip_positions(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return every position recorded inside the trip's time window.

    For ongoing trips the upper bound is "now".
    """
    t, _ = await own_trip(db, user, trip_id)

    end = _effective_end(t)
    rows = await positions_in_window_capped(db, t.device_id, t.started_at, end)
    logger.debug(
        "trip_positions user_id=%s trip_id=%s count=%d", user.id, trip_id, len(rows)
    )
    return [PositionOut.model_validate(p) for p in rows]


@router.get("/trips/{trip_id}/places", response_model=list[PlaceOut])
async def trip_places(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return every place linked to this trip via the ``place_trips`` junction.

    Read-only inverse of ``PATCH /places/{id}`` with ``trip_ids``. Useful as a
    convenience query; the same set is also derivable client-side from the
    ``trip_ids`` field on each place.
    """
    t, _ = await own_trip(db, user, trip_id)
    # Query Place directly so the `trips` relationship is selectin-loaded for
    # serialisation; going via t.places would yield Place rows whose `trips`
    # is unloaded and would trigger sync IO inside _place_out.
    rows = (
        await db.scalars(
            select(Place)
            .join(place_trips_t, place_trips_t.c.place_id == Place.id)
            .where(place_trips_t.c.trip_id == t.id),
        )
    ).all()
    logger.debug(
        "trip_places user_id=%s trip_id=%s count=%d", user.id, trip_id, len(rows)
    )
    return [_place_out(p) for p in rows]


@router.get("/trips/{trip_id}/export.gpx")
async def export_trip_gpx(
    trip_id: PrefixUUID,
    include_metadata: bool = Query(default=True),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export trip positions as a GPX file."""
    t, _ = await own_trip(db, user, trip_id)
    end = _effective_end(t)
    pts = await positions_in_window_capped(db, t.device_id, t.started_at, end)
    logger.info(
        "export_trip_gpx user_id=%s trip_id=%s points=%d include_metadata=%s",
        user.id,
        trip_id,
        len(pts),
        include_metadata,
    )
    return StreamingResponse(
        analytics.to_gpx(pts, name=t.name, include_metadata=include_metadata),
        media_type="application/gpx+xml",
        headers=_attach(f"{t.name}_export", "gpx"),
    )


@router.get("/trips/{trip_id}/export.csv")
async def export_trip_csv(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export trip positions as a CSV file."""
    t, _ = await own_trip(db, user, trip_id)
    end = _effective_end(t)
    pts = await positions_in_window_capped(db, t.device_id, t.started_at, end)
    logger.info(
        "export_trip_csv user_id=%s trip_id=%s points=%d",
        user.id,
        trip_id,
        len(pts),
    )
    return StreamingResponse(
        analytics.to_csv(pts),
        media_type="text/csv",
        headers=_attach(f"{t.name}_export", "csv"),
    )
