"""Media file serving."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import (
    OvernightSpot,
    OvernightSpotMedia,
    Place,
    PlaceMedia,
    User,
)

from ..deps import current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


async def _own_media(
    db: AsyncSession,
    user: User,
    media_id: PrefixUUID,
) -> tuple[PlaceMedia | OvernightSpotMedia, Place | OvernightSpot, str]:
    """Get media and verify ownership. Returns (media, entity, entity_type)."""
    # Check PlaceMedia first
    m = await db.scalar(select(PlaceMedia).where(PlaceMedia.public_id == media_id))
    if m and m.user_id == user.id:
        p = await db.scalar(select(Place).where(Place.id == m.place_id))
        if p:
            return m, p, "place"

    # Check OvernightSpotMedia
    m = await db.scalar(
        select(OvernightSpotMedia).where(OvernightSpotMedia.public_id == media_id),
    )
    if not m or m.user_id != user.id:
        raise HTTPException(404, "media not found")
    s = await db.scalar(
        select(OvernightSpot).where(OvernightSpot.id == m.overnight_spot_id),
    )
    if not s:
        raise HTTPException(404, "overnight spot not found")
    return m, s, "overnight_spot"


@router.get("/media/{media_id}/serve")
async def serve_media(
    media_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve a media file (image/video)."""
    m, entity, _entity_type = await _own_media(db, user, media_id)

    data_dir = AppConfig.data_dir or "/data"
    media_dir = Path(data_dir) / "uploads" / str(entity.user_id) / str(entity.public_id)
    file_path = media_dir / m.filename_stored

    if not file_path.resolve().is_relative_to(Path(data_dir).resolve()):
        raise HTTPException(404, "file not found")

    if not file_path.exists():
        raise HTTPException(404, "file not found")

    return FileResponse(
        file_path,
        media_type=m.mime_type,
        filename=m.filename_original,
        headers={"Cache-Control": "private, max-age=86400"},
    )
