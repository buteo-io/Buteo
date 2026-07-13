"""Ownership lookup helpers.

All endpoints address resources by their public UUID (``public_id``). These
helpers resolve the row, assert the requesting user owns it, and return the
ORM object — or raise 404 (never 403, to avoid leaking existence).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import Device, Entity, Place, Trip, User


def _as_prefixed_id(value: PrefixUUID | str, prefix: str) -> str | None:
    val_str = str(value)
    to_validate = val_str
    if len(val_str) > 36 and val_str[:3] == prefix:
        to_validate = val_str[3:]
    try:
        uuid.UUID(to_validate)
        if not val_str.startswith(prefix):
            val_str = f"{prefix}{val_str}"
        return val_str
    except (TypeError, ValueError):
        return None


def _not_found(kind: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{kind} not found")


async def own_device(
    db: AsyncSession,
    user: User,
    device_pid: PrefixUUID | str,
) -> Device:
    pid = _as_prefixed_id(device_pid, "dev")
    if pid is None:
        raise _not_found("device")
    d = await db.scalar(
        select(Device).join(Device.entity).where(Device.public_id == pid, Entity.user_id == user.id),
    )
    if not d or d.revoked_at is not None:
        raise _not_found("device")
    return d


async def own_place(db: AsyncSession, user: User, place_pid: PrefixUUID | str) -> Place:
    pid = _as_prefixed_id(place_pid, "plc")
    if pid is None:
        raise _not_found("place")
    p = await db.scalar(select(Place).where(Place.public_id == pid))
    if not p or p.user_id != user.id:
        raise _not_found("place")
    return p


async def own_trip(
    db: AsyncSession,
    user: User,
    trip_pid: PrefixUUID | str,
) -> tuple[Trip, Device]:
    pid = _as_prefixed_id(trip_pid, "trp")
    if pid is None:
        raise _not_found("trip")
    # Fetch Trip and Device in a single joint query
    result = await db.execute(
        select(Trip, Device)
        .join(Device, Device.id == Trip.device_id)
        .join(Entity, Entity.id == Device.entity_id)
        .where(Trip.public_id == pid, Entity.user_id == user.id),
    )
    row = result.first()
    if not row:
        raise _not_found("trip")
    return row[0], row[1]
