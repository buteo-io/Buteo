"""Entity listing and details router. Read-only for now."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import Entity, User

from ..deps import current_user, get_db
from ..schemas import UTCModel
from .devices import DeviceOut

logger = logging.getLogger(__name__)

router = APIRouter()


class EntityOut(UTCModel):
    """Wire shape for an entity."""

    id: PrefixUUID  # public_id
    type: str
    name: str
    avatar_icon: str | None = None
    metadata: dict | None = None
    devices: list[DeviceOut] = Field(default_factory=list)


@router.get("/entities", response_model=list[EntityOut])
async def list_entities(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EntityOut]:
    """List all entities owned by the caller, including their devices."""
    rows = (
        await db.scalars(
            select(Entity).options(selectinload(Entity.devices)).where(Entity.user_id == user.id).order_by(Entity.id),
        )
    ).all()
    logger.debug("list_entities user_id=%s count=%d", user.id, len(rows))
    return [
        EntityOut(
            id=ent.public_id,
            type=ent.type,
            name=ent.name,
            avatar_icon=ent.avatar_icon,
            metadata=ent.metadata_json,
            devices=[
                DeviceOut(
                    id=d.public_id,
                    entity_id=ent.public_id,
                    imei=d.imei,
                    name=d.name,
                    last_seen_at=d.last_seen_at,
                )
                for d in ent.devices
                if d.revoked_at is None
            ],
        )
        for ent in rows
    ]


@router.get("/entities/{entity_pid}", response_model=EntityOut)
async def get_entity(
    entity_pid: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EntityOut:
    """Get details of a single owned entity."""
    ent = await db.scalar(
        select(Entity)
        .options(selectinload(Entity.devices))
        .where(Entity.public_id == entity_pid, Entity.user_id == user.id),
    )
    if not ent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")

    return EntityOut(
        id=ent.public_id,
        type=ent.type,
        name=ent.name,
        avatar_icon=ent.avatar_icon,
        metadata=ent.metadata_json,
        devices=[
            DeviceOut(
                id=d.public_id,
                entity_id=ent.public_id,
                imei=d.imei,
                name=d.name,
                last_seen_at=d.last_seen_at,
            )
            for d in ent.devices
            if d.revoked_at is None
        ],
    )
