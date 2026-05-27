"""Public unauthenticated share endpoint."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import (
    OvernightSpot,
    OvernightSpotMedia,
    Place,
    PlaceMedia,
    Position,
    ShareLink,
    share_link_overnight_spots,
    share_link_places,
)
from tracker_core.store.security import hash_share_token

from ..deps import get_db
from ..limiter import limiter
from ..schemas import UTCModel

logger = logging.getLogger(__name__)

router = APIRouter()


class PublicPlaceMediaOut(BaseModel):
    """Public place media info."""

    id: PrefixUUID
    media_type: str
    mime_type: str


class PublicOvernightSpotMediaOut(BaseModel):
    """Public overnight spot media info."""

    id: PrefixUUID
    media_type: str
    mime_type: str


class PublicPlaceOut(BaseModel):
    """Public place info (no user-identifying data)."""

    id: PrefixUUID
    name: str
    notes: str | None = None
    lon: float
    lat: float
    place_category: str
    media: list[PublicPlaceMediaOut] = []


class PublicOvernightSpotOut(BaseModel):
    """Public overnight spot info."""

    id: PrefixUUID
    name: str
    notes: str | None = None
    lon: float
    lat: float
    nights_count: int
    media: list[PublicOvernightSpotMediaOut] = []


class PublicPositionOut(UTCModel):
    """Position with optional coordinate degradation."""

    time_id: datetime
    lon: float
    lat: float


class PublicShareOut(UTCModel):
    """Public share data."""

    trip_name: str
    trip_description: str | None
    started_at: datetime
    ended_at: datetime | None
    blur_meters: int
    positions: list[PublicPositionOut]
    places: list[PublicPlaceOut]
    overnight_spots: list[PublicOvernightSpotOut] = []


def _degrade_coordinate(coord: float, meters: int, lat: float | None = None) -> float:
    """Degrade coordinate precision by rounding to nearest N meters.

    Args:
        coord: lat or lon
        meters: degradation distance (0 = no degradation)
        lat: Optional latitude for longitude scaling

    Returns:
        Degraded coordinate
    """
    if meters == 0:
        return coord

    import math

    if lat is not None:
        degrees_per_meter = 1 / (111320 * math.cos(math.radians(lat)))
    else:
        degrees_per_meter = 1 / 111320

    degrees = meters * degrees_per_meter
    return round(coord / degrees) * degrees


def _align_timezone(dt: datetime, reference: datetime) -> datetime:
    """Align datetime tz-awareness to match reference for safe comparisons."""
    if reference.tzinfo is None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    if reference.tzinfo is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _effective_share_window(
    link: ShareLink, now_utc: datetime
) -> tuple[datetime, datetime]:
    """Clamp effective share window to trip bounds + delay cutoff."""
    trip = link.trip
    trip_start = trip.started_at
    trip_end = trip.ended_at or _align_timezone(now_utc, trip_start)

    start = trip_start
    if link.share_started_at is not None:
        start = max(trip_start, _align_timezone(link.share_started_at, trip_start))

    end = trip_end
    if link.share_ended_at is not None:
        end = min(trip_end, _align_timezone(link.share_ended_at, trip_end))

    if link.delay_hours > 0:
        cutoff = _align_timezone(now_utc - timedelta(hours=link.delay_hours), end)
        end = min(end, cutoff)

    return start, end


@router.get("/share/{token}", response_model=PublicShareOut)
@limiter.limit("30/minute;300/hour")
async def get_public_share(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> PublicShareOut:
    """Get public share data by token (no auth required)."""
    _ = request
    stmt = (
        select(ShareLink)
        .options(
            selectinload(ShareLink.trip),
            selectinload(ShareLink.selected_places),
            selectinload(ShareLink.selected_overnight_spots),
        )
        .where(ShareLink.token == hash_share_token(token))
    )
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()

    if not link or not link.is_active:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Share link not found or inactive"
        )

    trip = link.trip
    now_utc = datetime.now(timezone.utc)
    start, end = _effective_share_window(link, now_utc)

    positions = []
    if end >= start:
        count_stmt = (
            select(func.count())
            .select_from(Position)
            .where(
                Position.device_id == trip.device_id,
                Position.is_filtered.is_(False),
            )
            .where(Position.time_id >= start)
            .where(Position.time_id <= end)
        )
        total_count = (await db.scalar(count_stmt)) or 0

        MAX_SHARE_POINTS = 20_000

        if total_count <= MAX_SHARE_POINTS:
            stmt = (
                select(Position)
                .where(
                    Position.device_id == trip.device_id,
                    Position.is_filtered.is_(False),
                )
                .where(Position.time_id >= start)
                .where(Position.time_id <= end)
                .order_by(Position.time_id)
            )
            result = await db.execute(stmt)
            positions = result.scalars().all()
        else:
            import math

            step = math.ceil(total_count / MAX_SHARE_POINTS)
            subq = (
                select(
                    Position.id.label("pos_id"),
                    func.row_number().over(order_by=Position.time_id).label("row_num"),
                )
                .where(
                    Position.device_id == trip.device_id,
                    Position.is_filtered.is_(False),
                )
                .where(Position.time_id >= start)
                .where(Position.time_id <= end)
            ).subquery()

            sampled_ids_stmt = select(subq.c.pos_id).where(subq.c.row_num % step == 1)
            sampled_ids = (await db.execute(sampled_ids_stmt)).scalars().all()

            if sampled_ids:
                stmt = (
                    select(Position)
                    .where(Position.id.in_(sampled_ids))
                    .order_by(Position.time_id)
                )
                result = await db.execute(stmt)
                positions = result.scalars().all()

    degraded_positions = [
        PublicPositionOut(
            time_id=p.time_id,
            lon=_degrade_coordinate(p.lon, link.blur_meters, lat=p.lat),
            lat=_degrade_coordinate(p.lat, link.blur_meters),
        )
        for p in positions
    ]

    place_ids = [place.id for place in link.selected_places]
    media_by_place = {}
    if place_ids:
        media_stmt = await db.execute(
            select(PlaceMedia).where(PlaceMedia.place_id.in_(place_ids))
        )
        for m in media_stmt.scalars().all():
            media_by_place.setdefault(m.place_id, []).append(m)

    places_out = []
    for place in link.selected_places:
        place_media = media_by_place.get(place.id, [])
        media_out = [
            PublicPlaceMediaOut(
                id=m.public_id,
                media_type=m.media_type,
                mime_type=m.mime_type,
            )
            for m in place_media
        ]
        places_out.append(
            PublicPlaceOut(
                id=place.public_id,
                name=place.name,
                notes=place.notes,
                lon=_degrade_coordinate(place.lon, link.blur_meters, lat=place.lat),
                lat=_degrade_coordinate(place.lat, link.blur_meters),
                place_category=place.place_category,
                media=media_out,
            ),
        )

    spot_ids = [spot.id for spot in link.selected_overnight_spots]
    media_by_spot = {}
    if spot_ids:
        media_stmt = await db.execute(
            select(OvernightSpotMedia).where(
                OvernightSpotMedia.overnight_spot_id.in_(spot_ids)
            )
        )
        for m in media_stmt.scalars().all():
            media_by_spot.setdefault(m.overnight_spot_id, []).append(m)

    overnight_spots_out = []
    for spot in link.selected_overnight_spots:
        # Filter by delay: hide spots where the last night occurred after the cutoff
        if spot.last_stay_at is not None:
            spot_last_stay = _align_timezone(spot.last_stay_at, end)
            if spot_last_stay > end:
                continue

        spot_media = media_by_spot.get(spot.id, [])
        media_out = [
            PublicOvernightSpotMediaOut(
                id=m.public_id,
                media_type=m.media_type,
                mime_type=m.mime_type,
            )
            for m in spot_media
        ]
        overnight_spots_out.append(
            PublicOvernightSpotOut(
                id=spot.public_id,
                name=spot.name,
                notes=spot.notes,
                lon=_degrade_coordinate(spot.lon, link.blur_meters, lat=spot.lat),
                lat=_degrade_coordinate(spot.lat, link.blur_meters),
                nights_count=spot.nights_count,
                media=media_out,
            ),
        )

    return PublicShareOut(
        trip_name=trip.name,
        trip_description=trip.description,
        started_at=start,
        ended_at=end,
        blur_meters=link.blur_meters,
        positions=degraded_positions,
        places=places_out,
        overnight_spots=overnight_spots_out,
    )


@router.get("/share/{token}/media/{media_id}")
@limiter.limit("30/minute;300/hour")
async def serve_share_media(
    request: Request,
    token: str,
    media_id: PrefixUUID,
    db: AsyncSession = Depends(get_db),
):
    """Serve media for a public share (no auth required)."""
    _ = request
    stmt = (
        select(ShareLink)
        .options(
            selectinload(ShareLink.trip),
        )
        .where(ShareLink.token == hash_share_token(token))
    )
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()

    if not link or not link.is_active:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Share link not found or inactive"
        )

    # Check PlaceMedia first
    media_stmt = await db.execute(
        select(PlaceMedia).where(PlaceMedia.public_id == media_id)
    )
    media = media_stmt.scalar_one_or_none()
    entity = None

    if media:
        place_stmt = await db.execute(
            select(Place)
            .join(share_link_places, share_link_places.c.place_id == Place.id)
            .where(
                Place.id == media.place_id,
                share_link_places.c.share_link_id == link.id,
            )
        )
        place = place_stmt.scalar_one_or_none()
        if place:
            entity = place

    # Check OvernightSpotMedia if not found in places
    if not entity:
        media_stmt = await db.execute(
            select(OvernightSpotMedia).where(OvernightSpotMedia.public_id == media_id)
        )
        media = media_stmt.scalar_one_or_none()
        if media:
            spot_stmt = await db.execute(
                select(OvernightSpot)
                .join(
                    share_link_overnight_spots,
                    share_link_overnight_spots.c.overnight_spot_id == OvernightSpot.id,
                )
                .where(
                    OvernightSpot.id == media.overnight_spot_id,
                    share_link_overnight_spots.c.share_link_id == link.id,
                )
            )
            spot = spot_stmt.scalar_one_or_none()
            if spot:
                # Calculate effective share window end
                now_utc = datetime.now(timezone.utc)
                _, end = _effective_share_window(link, now_utc)

                # If OvernightSpotMedia, check delay limit
                if spot.last_stay_at is not None:
                    spot_last_stay = _align_timezone(spot.last_stay_at, end)
                    if spot_last_stay > end:
                        raise HTTPException(
                            status.HTTP_404_NOT_FOUND, "Media not found"
                        )

                entity = spot

    if not media or not entity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")

    data_dir = AppConfig.data_dir or "/data"
    media_dir = Path(data_dir) / "uploads" / str(entity.user_id) / str(entity.public_id)
    file_path = media_dir / media.filename_stored

    if not file_path.resolve().is_relative_to(Path(data_dir).resolve()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")

    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")

    return FileResponse(
        file_path,
        media_type=media.mime_type,
        filename=media.filename_original,
        headers={"Cache-Control": "private, max-age=86400"},
    )
