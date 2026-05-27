"""Public share links for trips with privacy filters."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import (
    OvernightSpot,
    Place,
    ShareLink,
    Trip,
    User,
)
from tracker_core.store.security import hash_share_token

from ..deps import current_user, get_current_tenant_id, get_db, own_trip
from ..schemas import UTCModel

logger = logging.getLogger(__name__)

router = APIRouter()


class ShareLinkIn(BaseModel):
    """Create new share link."""

    trip_id: PrefixUUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    share_started_at: datetime | None = None
    share_ended_at: datetime | None = None
    delay_hours: int = Field(default=72, ge=0)
    blur_meters: int = Field(default=100, ge=0)
    is_active: bool = True
    place_ids: list[PrefixUUID] = Field(default_factory=list)
    overnight_spot_ids: list[PrefixUUID] = Field(default_factory=list)


class ShareLinkUpdateIn(BaseModel):
    """Partial update for PATCH /share-links/{id}."""

    model_config = {"extra": "forbid"}

    trip_id: PrefixUUID | None = Field(default=None)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    share_started_at: datetime | None = None
    share_ended_at: datetime | None = None
    delay_hours: int | None = Field(default=None, ge=0)
    blur_meters: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    place_ids: list[PrefixUUID] | None = None
    overnight_spot_ids: list[PrefixUUID] | None = None


class ShareLinkOut(UTCModel):
    """Share link response."""

    id: PrefixUUID
    trip_id: PrefixUUID
    name: str
    description: str | None
    share_started_at: datetime | None
    share_ended_at: datetime | None
    delay_hours: int
    blur_meters: int
    is_active: bool
    place_ids: list[PrefixUUID]
    overnight_spot_ids: list[PrefixUUID]
    created_at: datetime
    updated_at: datetime


class ShareLinkSecretOut(ShareLinkOut):
    """Share link response that includes clear-text token.

    Used only on token-issuing endpoints (create + rotate).
    """

    token: str


def _out(link: ShareLink) -> ShareLinkOut:
    return ShareLinkOut(
        id=link.public_id,
        trip_id=link.trip.public_id,
        name=link.name,
        description=link.description,
        share_started_at=link.share_started_at,
        share_ended_at=link.share_ended_at,
        delay_hours=link.delay_hours,
        blur_meters=link.blur_meters,
        is_active=link.is_active,
        place_ids=[p.public_id for p in link.selected_places],
        overnight_spot_ids=[s.public_id for s in link.selected_overnight_spots],
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _out_with_token(link: ShareLink, token: str) -> ShareLinkSecretOut:
    return ShareLinkSecretOut(token=token, **_out(link).model_dump())


async def _resolve_share_places(
    db: AsyncSession,
    user: User,
    trip: Trip,
    place_ids: list[PrefixUUID],
) -> list[Place]:
    """Resolve places for share link with ownership + trip constraints.

    Every requested place must be owned by caller and linked to target trip.
    """
    if not place_ids:
        return []
    uniq = list(set(place_ids))
    stmt = (
        select(Place)
        .join(place_trips, place_trips.c.place_id == Place.id)
        .where(
            Place.public_id.in_(uniq),
            Place.user_id == user.id,
            place_trips.c.trip_id == trip.id,
        )
    )
    result = await db.execute(stmt)
    places = result.scalars().all()
    if len(places) != len(uniq):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "place not found")
    return list(places)


async def _resolve_share_overnight_spots(
    db: AsyncSession,
    user: User,
    trip: Trip,
    spot_ids: list[PrefixUUID],
) -> list[OvernightSpot]:
    """Resolve overnight spots for share link with ownership + trip constraints.

    Every requested spot must be owned by caller (via trip) and linked to target trip.
    """
    if not spot_ids:
        return []
    uniq = list(set(spot_ids))
    stmt = select(OvernightSpot).where(
        OvernightSpot.public_id.in_(uniq),
        OvernightSpot.trip_id == trip.id,
    )
    result = await db.execute(stmt)
    spots = result.scalars().all()
    if len(spots) != len(uniq):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "overnight spot not found")
    return list(spots)


async def _apply_share_link_update(
    db: AsyncSession,
    user: User,
    link: ShareLink,
    data: ShareLinkUpdateIn,
) -> None:
    fields = data.model_fields_set
    if "trip_id" in fields:
        if data.trip_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "trip_id cannot be null")
        trip, _ = await own_trip(db, user, data.trip_id)
        link.trip_id = trip.id
    if "name" in fields:
        if data.name is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "name cannot be null")
        stmt = select(ShareLink).where(
            ShareLink.user_id == user.id,
            ShareLink.name == data.name,
            ShareLink.id != link.id,
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Share link with this name already exists",
            )
        link.name = data.name
    if "description" in fields:
        link.description = data.description
    if "share_started_at" in fields:
        link.share_started_at = data.share_started_at
    if "share_ended_at" in fields:
        link.share_ended_at = data.share_ended_at
    if "delay_hours" in fields:
        if data.delay_hours is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "delay_hours cannot be null"
            )
        link.delay_hours = data.delay_hours
    if "blur_meters" in fields:
        if data.blur_meters is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "blur_meters cannot be null"
            )
        link.blur_meters = data.blur_meters
    if "is_active" in fields:
        if data.is_active is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "is_active cannot be null")
        link.is_active = data.is_active
    if "place_ids" in fields:
        if data.place_ids is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "place_ids cannot be null")
        link.selected_places = await _resolve_share_places(
            db, user, link.trip, data.place_ids
        )
    if "overnight_spot_ids" in fields:
        if data.overnight_spot_ids is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "overnight_spot_ids cannot be null"
            )
        link.selected_overnight_spots = await _resolve_share_overnight_spots(
            db,
            user,
            link.trip,
            data.overnight_spot_ids,
        )


@router.get("/share-links", response_model=list[ShareLinkOut])
async def list_share_links(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ShareLinkOut]:
    """List all share links for current user."""
    stmt = (
        select(ShareLink)
        .options(selectinload(ShareLink.trip))
        .where(ShareLink.user_id == user.id)
        .order_by(ShareLink.created_at.desc())
    )
    result = await db.execute(stmt)
    links = result.scalars().all()
    return [_out(link) for link in links]


@router.post(
    "/share-links",
    response_model=ShareLinkSecretOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_share_link(
    data: ShareLinkIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ShareLinkSecretOut:
    """Create new share link for a trip."""
    trip, _ = await own_trip(db, user, data.trip_id)

    stmt = select(ShareLink).where(
        ShareLink.user_id == user.id,
        ShareLink.name == data.name,
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Share link with this name already exists",
        )

    clear_token = secrets.token_urlsafe(32)
    token = f"{tenant_id}_{clear_token}"

    link = ShareLink(
        user_id=user.id,
        trip_id=trip.id,
        token=hash_share_token(token),
        name=data.name,
        description=data.description,
        share_started_at=data.share_started_at,
        share_ended_at=data.share_ended_at,
        delay_hours=data.delay_hours,
        blur_meters=data.blur_meters,
        is_active=data.is_active,
    )

    if data.place_ids:
        link.selected_places = await _resolve_share_places(
            db, user, trip, data.place_ids
        )
    if data.overnight_spot_ids:
        link.selected_overnight_spots = await _resolve_share_overnight_spots(
            db, user, trip, data.overnight_spot_ids
        )

    db.add(link)
    await db.commit()
    await db.refresh(link)

    return _out_with_token(link, token)


@router.get("/share-links/{link_id}", response_model=ShareLinkOut)
async def get_share_link(
    link_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareLinkOut:
    """Get single share link by ID."""
    stmt = select(ShareLink).where(ShareLink.public_id == link_id)
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    return _out(link)


@router.patch("/share-links/{link_id}", response_model=ShareLinkOut)
async def update_share_link(
    link_id: PrefixUUID,
    data: ShareLinkUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareLinkOut:
    """Update share link."""
    stmt = (
        select(ShareLink)
        .options(selectinload(ShareLink.trip))
        .where(ShareLink.public_id == link_id)
    )
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    await _apply_share_link_update(db, user, link, data)

    link.updated_at = datetime.now(timezone.utc)
    await db.commit()

    stmt = (
        select(ShareLink)
        .options(selectinload(ShareLink.trip))
        .where(ShareLink.id == link.id)
    )
    result = await db.execute(stmt)
    link = result.scalar_one()

    return _out(link)


@router.post("/share-links/{link_id}/rotate", response_model=ShareLinkSecretOut)
async def rotate_share_link(
    link_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ShareLinkSecretOut:
    """Rotate share token and return new clear-text token once."""
    stmt = (
        select(ShareLink)
        .options(selectinload(ShareLink.trip))
        .where(ShareLink.public_id == link_id)
    )
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    clear_token = secrets.token_urlsafe(32)
    token = f"{tenant_id}_{clear_token}"
    link.token = hash_share_token(token)
    link.updated_at = datetime.now(timezone.utc)
    await db.commit()

    stmt = (
        select(ShareLink)
        .options(selectinload(ShareLink.trip))
        .where(ShareLink.id == link.id)
    )
    result = await db.execute(stmt)
    link = result.scalar_one()
    return _out_with_token(link, token)


@router.post("/share-links/{link_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_link(
    link_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke share link by setting it inactive."""
    stmt = select(ShareLink).where(ShareLink.public_id == link_id)
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if not link.is_active:
        return

    link.is_active = False
    link.updated_at = datetime.now(timezone.utc)
    await db.commit()


@router.delete("/share-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share_link(
    link_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete share link."""
    stmt = select(ShareLink).where(ShareLink.public_id == link_id)
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if link.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    await db.delete(link)
    await db.commit()
