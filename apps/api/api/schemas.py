"""Shared Pydantic response schemas used across routers."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, model_validator


class UTCModel(BaseModel):
    """Base model that ensures all datetime fields are serialised with UTC tzinfo.

    SQLite + aiosqlite returns naive datetimes even for ``DateTime(timezone=True)``
    columns. Without this fix JS receives strings like ``"2026-05-10T22:30:00"``
    which are interpreted as *local* time, causing a ±offset-hour display error.
    """

    @model_validator(mode="after")
    def _stamp_utc(self) -> UTCModel:
        for field in self.model_fields:
            v = getattr(self, field)
            if isinstance(v, datetime) and v.tzinfo is None:
                setattr(self, field, v.replace(tzinfo=timezone.utc))
        return self


class PositionOut(UTCModel):
    """Wire shape for a single GPS fix.

    Uses ``from_attributes`` so we can build it directly from a SQLAlchemy
    ``Position`` row via ``PositionOut.model_validate(row)``.
    """

    model_config = ConfigDict(from_attributes=True)

    time_id: datetime
    lon: float
    lat: float
    altitude: float | None = None
    speed: float | None = None
    satellites: int | None = None
