"""Overnight spot management endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.overnight_service import detect_and_persist_overnights
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import (
    Device,
    Entity,
    OvernightSpot,
    OvernightSpotMedia,
    Trip,
    User,
)

from ..deps import current_user, get_db, own_trip
from ..limiter import limiter
from ..media_utils import (
    ALLOWED_IMAGE_MIMES,
    ALLOWED_MIMES,
    ALLOWED_VIDEO_MIMES,
    validate_magic_bytes,
)
from ..schemas import UTCModel

logger = logging.getLogger(__name__)

router = APIRouter()


class OvernightSpotOut(UTCModel):
    """Overnight spot output schema."""

    id: PrefixUUID
    trip_id: PrefixUUID
    name: str
    notes: str | None
    lon: float
    lat: float
    nights_count: int
    last_stay_at: datetime
    created_at: datetime
    media: list[OvernightSpotMediaOut] = Field(default_factory=list)


class OvernightSpotUpdateIn(BaseModel):
    """Overnight spot update input (name and notes only)."""

    name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class OvernightSpotDetectOut(UTCModel):
    status: str
    created: int
    updated: int
    last_checked_position_time: datetime | None


class OvernightSpotMediaOut(BaseModel):
    """Overnight spot media output schema."""

    id: PrefixUUID
    filename_original: str
    media_type: str
    mime_type: str
    size_bytes: int
    created_at: str


def _media_out(m: OvernightSpotMedia) -> OvernightSpotMediaOut:
    return OvernightSpotMediaOut(
        id=m.public_id,
        filename_original=m.filename_original,
        media_type=m.media_type,
        mime_type=m.mime_type,
        size_bytes=m.size_bytes,
        created_at=m.created_at.isoformat(),
    )


def _get_media_dir(spot: OvernightSpot) -> Path:
    data_dir = AppConfig.data_dir or "/data"
    return Path(data_dir) / "uploads" / str(spot.user_id) / str(spot.public_id)


async def _own_overnight_spot(
    db: AsyncSession, user: User, spot_id: PrefixUUID
) -> tuple[OvernightSpot, PrefixUUID]:
    """Fetch overnight spot and verify ownership via trip -> device -> user."""
    row = (
        await db.execute(
            select(OvernightSpot, Trip.public_id)
            .join(Trip, Trip.id == OvernightSpot.trip_id)
            .join(Device, Device.id == Trip.device_id)
            .join(Entity, Entity.id == Device.entity_id)
            .where(OvernightSpot.public_id == spot_id, Entity.user_id == user.id),
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "overnight spot not found")
    return row


def _out(
    spot: OvernightSpot,
    trip_public_id: PrefixUUID,
    media_list: list[OvernightSpotMedia] | None = None,
) -> OvernightSpotOut:
    """Convert OvernightSpot model to output schema."""
    return OvernightSpotOut(
        id=spot.public_id,
        trip_id=trip_public_id,
        name=spot.name,
        notes=spot.notes,
        lon=spot.lon,
        lat=spot.lat,
        nights_count=spot.nights_count,
        last_stay_at=spot.last_stay_at,
        created_at=spot.created_at,
        media=[_media_out(m) for m in (media_list or [])],
    )


@router.post(
    "/trips/{trip_id}/overnight-spots/detect", response_model=OvernightSpotDetectOut
)
async def detect_overnight_spots(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run overnight spot detection for this trip if new data exists."""
    trip, _ = await own_trip(db, user, trip_id)
    result = await detect_and_persist_overnights(db, trip, user)
    logger.info(
        "overnight_detect user_id=%s trip_id=%s status=%s created=%d updated=%d",
        user.id,
        trip_id,
        result.status,
        result.created,
        result.updated,
    )
    return OvernightSpotDetectOut(
        status=result.status,
        created=result.created,
        updated=result.updated,
        last_checked_position_time=result.last_checked_position_time,
    )


@router.get("/trips/{trip_id}/overnight-spots", response_model=list[OvernightSpotOut])
async def list_overnight_spots(
    trip_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all overnight spots for a trip."""
    trip, _ = await own_trip(db, user, trip_id)

    rows = (
        await db.execute(
            select(OvernightSpot, Trip.public_id)
            .join(Trip, Trip.id == OvernightSpot.trip_id)
            .where(OvernightSpot.trip_id == trip.id),
        )
    ).all()

    spot_ids = [spot.id for spot, _ in rows]
    media_by_spot: dict[int, list[OvernightSpotMedia]] = {}
    if spot_ids:
        media_rows = (
            await db.scalars(
                select(OvernightSpotMedia)
                .where(OvernightSpotMedia.overnight_spot_id.in_(spot_ids))
                .order_by(OvernightSpotMedia.created_at.desc())
            )
        ).all()
        for m in media_rows:
            media_by_spot.setdefault(m.overnight_spot_id, []).append(m)

    logger.debug(
        "list_overnight_spots user_id=%s trip_id=%s count=%d",
        user.id,
        trip_id,
        len(rows),
    )
    return [
        _out(spot, trip_public_id, media_by_spot.get(spot.id))
        for spot, trip_public_id in rows
    ]


@router.patch("/overnight-spots/{spot_id}", response_model=OvernightSpotOut)
async def update_overnight_spot(
    spot_id: PrefixUUID,
    body: OvernightSpotUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update overnight spot name and notes. Cannot delete overnight spots."""
    spot, trip_public_id = await _own_overnight_spot(db, user, spot_id)
    spot.name = body.name
    spot.notes = body.notes
    await db.commit()
    await db.refresh(spot)

    # Fetch media for the response
    media_stmt = await db.execute(
        select(OvernightSpotMedia)
        .where(OvernightSpotMedia.overnight_spot_id == spot.id)
        .order_by(OvernightSpotMedia.created_at.desc())
    )
    media = list(media_stmt.scalars().all())

    logger.info("overnight_spot_update user_id=%s spot_id=%s", user.id, spot_id)
    return _out(spot, trip_public_id, media)


@router.get(
    "/overnight-spots/{spot_id}/media", response_model=list[OvernightSpotMediaOut]
)
async def list_overnight_spot_media(
    spot_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all media for an overnight spot."""
    spot, _ = await _own_overnight_spot(db, user, spot_id)
    rows = (
        await db.scalars(
            select(OvernightSpotMedia)
            .where(
                OvernightSpotMedia.overnight_spot_id == spot.id,
                OvernightSpotMedia.user_id == user.id,
            )
            .order_by(OvernightSpotMedia.created_at.desc()),
        )
    ).all()
    return [_media_out(m) for m in rows]


@router.post("/overnight-spots/{spot_id}/media", response_model=OvernightSpotMediaOut)
@limiter.limit("10/minute;50/hour")
async def upload_overnight_spot_media(
    request: Request,
    spot_id: PrefixUUID,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload media (image/video) to an overnight spot."""
    spot, _ = await _own_overnight_spot(db, user, spot_id)

    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(400, "file type not allowed")

    if file.content_type in ALLOWED_IMAGE_MIMES:
        max_size = AppConfig.max_image_size_mb * 1024 * 1024
    elif file.content_type in ALLOWED_VIDEO_MIMES:
        max_size = AppConfig.max_video_size_mb * 1024 * 1024
    else:
        max_size = AppConfig.max_audio_size_mb * 1024 * 1024

    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(400, f"file too large (max {max_size // (1024 * 1024)}MB)")

    if not validate_magic_bytes(content, file.content_type):
        raise HTTPException(400, "file content does not match declared type")

    if file.content_type in ALLOWED_IMAGE_MIMES:
        media_type = "image"
    elif file.content_type in ALLOWED_VIDEO_MIMES:
        media_type = "video"
    else:
        media_type = "audio"
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/x-msvideo": "avi",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/ogg": "ogg",
        "audio/webm": "webm",
        "audio/x-m4a": "m4a",
    }.get(file.content_type, "bin")
    stored_filename = f"{uuid.uuid4()}.{ext}"

    media_dir = _get_media_dir(spot)
    media_dir.mkdir(parents=True, exist_ok=True)
    file_path = media_dir / stored_filename
    file_path.write_bytes(content)

    m = OvernightSpotMedia(
        overnight_spot_id=spot.id,
        user_id=user.id,
        filename_original=file.filename or "unknown",
        filename_stored=stored_filename,
        media_type=media_type,
        mime_type=file.content_type,
        size_bytes=len(content),
    )
    db.add(m)
    await db.commit()
    logger.info(
        "overnight_spot_media_upload user_id=%s spot_id=%s media_id=%s",
        user.id,
        spot_id,
        m.public_id,
    )
    return _media_out(m)


@router.delete("/overnight-spots/{spot_id}/media/{media_id}", status_code=204)
async def delete_overnight_spot_media(
    spot_id: PrefixUUID,
    media_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a media item from an overnight spot."""
    spot, _ = await _own_overnight_spot(db, user, spot_id)
    m = await db.scalar(
        select(OvernightSpotMedia).where(
            OvernightSpotMedia.public_id == media_id,
            OvernightSpotMedia.overnight_spot_id == spot.id,
            OvernightSpotMedia.user_id == user.id,
        ),
    )
    if not m:
        raise HTTPException(404, "media not found")

    media_dir = _get_media_dir(spot)
    file_path = media_dir / m.filename_stored
    if file_path.exists():
        file_path.unlink()

    await db.delete(m)
    await db.commit()
    logger.info(
        "overnight_spot_media_delete user_id=%s spot_id=%s media_id=%s",
        user.id,
        spot_id,
        media_id,
    )
