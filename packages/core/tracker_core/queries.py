"""Shared SQL query helpers used across multiple routers / ingest.

Kept tiny on purpose: only patterns that appeared in 3+ places.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker_core.store.models import Position

# Hard ceiling on rows materialised into Python by analytics / export
# endpoints. With high-frequency Codec 8 ingestion (one fix every few
# seconds) a 5-year window can hit tens of millions of rows, exhausting
# memory before the haversine pass even starts. Tuned empirically: 200k
# rows ~= 50 MB peak and covers ~12 days at 1 Hz, ~70 days at 5s, ~6 months
# at 60s. Keep in sync with frontend-side messaging (api.ts MAX_RANGE_HINT).
MAX_ANALYTICS_POINTS = 200_000


async def positions_in_window(
    db: AsyncSession,
    device_id: int,
    from_: datetime | None = None,
    to: datetime | None = None,
    limit: int | None = None,
) -> list[Position]:
    """Return positions for a device, ordered by time ascending.

    Optional time bounds and row limit. Same query previously duplicated in
    positions / analytics / share / trips routers.
    """
    q = select(Position).where(Position.device_id == device_id, Position.is_filtered.is_(False))
    if from_ is not None:
        q = q.where(Position.time_id >= from_)
    if to is not None:
        q = q.where(Position.time_id <= to)
    q = q.order_by(Position.time_id.asc())
    if limit is not None:
        q = q.limit(limit)
    return list((await db.scalars(q)).all())


async def positions_in_window_capped(
    db: AsyncSession,
    device_id: int,
    from_: datetime | None = None,
    to: datetime | None = None,
) -> list[Position]:
    """Like :func:`positions_in_window` but raise 413 over :data:`MAX_ANALYTICS_POINTS`.

    Used by analytics + export endpoints whose memory cost scales linearly
    with row count. Stats/exports are useless if silently truncated, so we
    refuse instead and ask the user to narrow their window.
    """
    rows = await positions_in_window(db, device_id, from_, to, limit=MAX_ANALYTICS_POINTS + 1)
    if len(rows) > MAX_ANALYTICS_POINTS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            (f"Window contains more than {MAX_ANALYTICS_POINTS:,} positions. Narrow the date range and try again."),
        )
    return rows


async def latest_position(db: AsyncSession, device_id: int) -> Position | None:
    return await db.scalar(
        select(Position)
        .where(Position.device_id == device_id, Position.is_filtered.is_(False))
        .order_by(Position.time_id.desc())
        .limit(1),
    )
