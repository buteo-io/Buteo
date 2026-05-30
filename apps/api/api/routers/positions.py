"""Position read endpoints for owned devices.

Writes come in through the ingest TCP server (``ingest.server``), not HTTP.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.queries import latest_position, positions_in_window
from tracker_core.store.ids import PrefixUUID
from tracker_core.store.models import User

from ..deps import current_user, get_db, own_device
from ..schemas import PositionOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/devices/{device_id}/positions/latest", response_model=PositionOut | None)
async def latest(
    device_id: PrefixUUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent fix for ``device_id``, or ``null`` if none yet.

    404 if the device is unknown or owned by somebody else.
    """
    d = await own_device(db, user, device_id)
    p = await latest_position(db, d.id)
    logger.info(
        "latest_position user_id=%s device_id=%s found=%s",
        user.id,
        device_id,
        p is not None,
    )
    return PositionOut.model_validate(p) if p else None


@router.get("/devices/{device_id}/positions", response_model=list[PositionOut])
async def history(
    device_id: PrefixUUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=5000, le=50000),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return positions for ``device_id`` in chronological order.

    Query params:
        from: inclusive lower bound (ISO-8601). Omit for "since forever".
        to:   inclusive upper bound.
        limit: max rows (cap 50 000) to protect the client from huge payloads.
    """
    d = await own_device(db, user, device_id)
    rows = await positions_in_window(db, d.id, from_, to, limit=limit)
    logger.info(
        "list_positions user_id=%s device_id=%s count=%d", user.id, device_id, len(rows)
    )
    return [PositionOut.model_validate(p) for p in rows]
