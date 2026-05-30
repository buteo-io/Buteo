"""Device listing. Registration is CLI-only; this module is read-only."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import Device, Entity, User

from ..deps import current_user, get_db
from ..schemas import UTCModel

logger = logging.getLogger(__name__)

router = APIRouter()


class DeviceOut(UTCModel):
    """Wire shape for a device. ``id`` is the public UUID, never the int PK."""

    id: PrefixUUID  # public_id
    entity_id: PrefixUUID
    imei: str
    name: str
    last_seen_at: datetime | None = None


@router.get("/devices")
async def list_devices(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[DeviceOut]:
    """List all non-revoked devices owned by the caller, ordered by creation."""
    from sqlalchemy.orm import selectinload

    rows = (
        await db.scalars(
            select(Device)
            .join(Device.entity)
            .options(selectinload(Device.entity))
            .where(Entity.user_id == user.id, Device.revoked_at.is_(None))
            .order_by(Device.id),
        )
    ).all()
    logger.debug("list_devices user_id=%s count=%d", user.id, len(rows))
    return [
        DeviceOut(
            id=d.public_id,
            entity_id=d.entity.public_id,
            imei=d.imei,
            name=d.name,
            last_seen_at=d.last_seen_at,
        )
        for d in rows
    ]
