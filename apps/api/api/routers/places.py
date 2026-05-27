"""User-marked places (POIs, drinking water, camping, parking, …).

A place may also be linked to any number of user trips via the
``place_trips`` junction. Linkage is edited from the place side
(``PATCH /places/{id}`` with ``trip_ids``); the trip side exposes the
inverse read-only list under ``GET /trips/{id}/places``.

Places can also have media (images/videos) attached.
"""

import logging
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import (
    Device,
    Entity,
    Place,
    PlaceMedia,
    Trip,
    User,
)

from ..deps import current_user, get_db, own_place
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


class PlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    notes: str | None = None
    place_category: Literal["POI", "Drinking Water", "Camping", "Parking"]
    # Public ids of trips this place belongs to. Server validates each one
    # is owned by the caller; unknown / foreign trip ids return 404.
    trip_ids: list[PrefixUUID] = Field(default_factory=list)


class PlaceMediaOut(BaseModel):
    id: PrefixUUID
    filename_original: str
    media_type: str
    mime_type: str
    size_bytes: int
    created_at: str


def _media_out(m: PlaceMedia) -> PlaceMediaOut:
    return PlaceMediaOut(
        id=m.public_id,
        filename_original=m.filename_original,
        media_type=m.media_type,
        mime_type=m.mime_type,
        size_bytes=m.size_bytes,
        created_at=m.created_at.isoformat(),
    )


class PlaceOut(UTCModel):
    id: PrefixUUID
    name: str
    lon: float
    lat: float
    notes: str | None = None
    place_category: str
    trip_ids: list[PrefixUUID] = Field(default_factory=list)
    media: list[PlaceMediaOut] = Field(default_factory=list)


def _out(p: Place, media_list: list[PlaceMedia] | None = None) -> PlaceOut:
    return PlaceOut(
        id=p.public_id,
        name=p.name,
        lon=p.lon,
        lat=p.lat,
        notes=p.notes,
        place_category=p.place_category,
        trip_ids=[t.public_id for t in (p.trips or [])],
        media=[_media_out(m) for m in (media_list or [])],
    )


async def _resolve_owned_trips(
    db: AsyncSession,
    user: User,
    trip_pids: list[PrefixUUID],
) -> list[Trip]:
    """Return Trip rows for ``trip_pids`` if every one is owned by ``user``.

    Ownership of a trip is via its device. We resolve all ids in one query
    and verify the count matches the request to reject any unknown / foreign
    ids with a single 404.
    """
    if not trip_pids:
        return []
    # Dedup while preserving order is unnecessary — the SET below ignores
    # order; the relationship list ordering reflects the DB's natural order.
    rows = (
        (
            await db.execute(
                select(Trip)
                .join(Device, Device.id == Trip.device_id)
                .join(Entity, Entity.id == Device.entity_id)
                .where(Trip.public_id.in_(trip_pids), Entity.user_id == user.id),
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(set(trip_pids)):
        raise HTTPException(404, "trip not found")
    return list(rows)


def _apply_scalars(p: Place, body: PlaceIn) -> None:
    p.name = body.name
    p.notes = body.notes
    p.place_category = body.place_category
    p.lon = body.lon
    p.lat = body.lat


@router.get("/places", response_model=list[PlaceOut])
async def list_places(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Return every place owned by the caller, newest first."""
    rows = (
        await db.scalars(
            select(Place).where(Place.user_id == user.id).order_by(Place.id.desc())
        )
    ).all()
    logger.debug("list_places user_id=%s count=%d", user.id, len(rows))
    place_ids = [p.id for p in rows]
    media_by_place: dict[int, list[PlaceMedia]] = {}
    if place_ids:
        media_rows = (
            await db.scalars(
                select(PlaceMedia).where(PlaceMedia.place_id.in_(place_ids))
            )
        ).all()
        for m in media_rows:
            media_by_place.setdefault(m.place_id, []).append(m)
    return [_out(p, media_by_place.get(p.id)) for p in rows]


@router.post("/places", response_model=PlaceOut)
async def create_place(
    body: PlaceIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a place for the caller. Coordinates are validated by Pydantic."""
    trips = await _resolve_owned_trips(db, user, body.trip_ids)
    p = Place(user_id=user.id)
    _apply_scalars(p, body)
    p.trips = trips
    db.add(p)
    await db.commit()
    logger.info(
        "place_create user_id=%s place_id=%s name=%r", user.id, p.public_id, body.name
    )
    # Don't refresh: refresh expires `trips` and the selectin re-load would
    # need an awaitable IO call outside the greenlet. expire_on_commit=False
    # keeps the in-memory instance usable as-is.
    return _out(p)


@router.patch("/places/{place_id}", response_model=PlaceOut)
async def update_place(
    place_id: PrefixUUID,
    body: PlaceIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace a place's fields. 404 if the place is not owned by the caller."""
    p = await own_place(db, user, place_id)
    trips = await _resolve_owned_trips(db, user, body.trip_ids)
    _apply_scalars(p, body)
    # Replace the full set; SQLAlchemy diffs and emits inserts/deletes on
    # the place_trips table.
    p.trips = trips
    await db.commit()
    logger.info("place_update user_id=%s place_id=%s", user.id, p.public_id)
    media_rows = (
        await db.scalars(select(PlaceMedia).where(PlaceMedia.place_id == p.id))
    ).all()
    return _out(p, list(media_rows))


@router.delete("/places/{place_id}", status_code=204)
async def delete_place(
    place_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a place. Idempotent: returns 204 whether found or not is rejected with 404."""
    p = await own_place(db, user, place_id)
    media_dir = _get_media_dir(p)
    await db.delete(p)
    await db.commit()
    if media_dir.exists():
        shutil.rmtree(media_dir, ignore_errors=True)
    logger.info("place_delete user_id=%s place_id=%s", user.id, place_id)


def _get_media_dir(place: Place) -> Path:
    data_dir = AppConfig.data_dir or "/data"
    return Path(data_dir) / "uploads" / str(place.user_id) / str(place.public_id)


@router.get("/places/{place_id}/media", response_model=list[PlaceMediaOut])
async def list_place_media(
    place_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all media for a place."""
    p = await own_place(db, user, place_id)
    rows = (
        await db.scalars(
            select(PlaceMedia)
            .where(PlaceMedia.place_id == p.id, PlaceMedia.user_id == user.id)
            .order_by(PlaceMedia.created_at.desc()),
        )
    ).all()
    return [_media_out(m) for m in rows]


@router.post("/places/{place_id}/media", response_model=PlaceMediaOut)
@limiter.limit("10/minute;50/hour")
async def upload_place_media(
    request: Request,
    place_id: PrefixUUID,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload media (image/video) to a place."""
    p = await own_place(db, user, place_id)

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
        raise HTTPException(413, f"file too large (max {max_size // (1024 * 1024)}MB)")

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

    media_dir = _get_media_dir(p)
    media_dir.mkdir(parents=True, exist_ok=True)
    file_path = media_dir / stored_filename
    file_path.write_bytes(content)

    m = PlaceMedia(
        place_id=p.id,
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
        "media_upload user_id=%s place_id=%s media_id=%s",
        user.id,
        p.public_id,
        m.public_id,
    )
    return _media_out(m)


@router.delete("/places/{place_id}/media/{media_id}", status_code=204)
async def delete_place_media(
    place_id: PrefixUUID,
    media_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a media item from a place."""
    p = await own_place(db, user, place_id)
    m = await db.scalar(
        select(PlaceMedia).where(
            PlaceMedia.public_id == media_id,
            PlaceMedia.place_id == p.id,
            PlaceMedia.user_id == user.id,
        ),
    )
    if not m:
        raise HTTPException(404, "media not found")

    media_dir = _get_media_dir(p)
    file_path = media_dir / m.filename_stored
    if file_path.exists():
        file_path.unlink()

    await db.delete(m)
    await db.commit()
    logger.info(
        "media_delete user_id=%s place_id=%s media_id=%s",
        user.id,
        p.public_id,
        media_id,
    )
