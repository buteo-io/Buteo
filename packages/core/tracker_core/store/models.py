"""SQLAlchemy ORM models for the tracker schema.

All user-facing resources expose a stable ``public_id`` UUID; the integer
primary key is internal only and never appears on the wire. Every row that
can be modified has ``created_at`` + ``updated_at`` timestamps (UTC).

Design notes for future contributors:

- Emails are stored lowercase; a ``CHECK`` constraint enforces it so we can
  rely on equality without ``LOWER()``.
- ``User.token_version`` is the JWT revocation counter: bump it on logout,
  password reset, or deactivation to invalidate all outstanding tokens.
- ``Device.revoked_at`` is the soft-delete marker. The ingest server refuses
  packets from revoked devices; the API hides them from listings.
- Ownership of a :class:`Trip` is derived via its :class:`Device`
  (``device.user_id``). Do **not** duplicate ``user_id`` on these tables —
  see the ownership helpers in ``api/ownership.py``.
- Position/lat/lon range checks live in the DB (``CHECK`` constraints) so
  bad data from the ingest path is rejected even if the parser is buggy.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core_db import CoreBase as Base
from .ids import gen_public_id


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class User(Base):
    """Local account. One per human.

    Public sign-up is intentionally disabled — users are provisioned via the
    CLI (``python -m tracker_core.cli.manage create-user``). This is a deliberate
    gatekeeper for the self-hosted + hosted product split.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="usr"),
    )
    # email stored lowercase; CITEXT would also work, but lower() + unique covers it
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    # bumped on logout / password reset to invalidate outstanding JWTs
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    entities: Mapped[list[Entity]] = relationship(back_populates="user", cascade="all,delete-orphan")

    __table_args__ = (CheckConstraint("email = lower(email)", name="users_email_lowercase"),)


class Entity(Base):
    """Generic tracked entity owned by a user (vehicle, pet, person, tracker, asset, etc.).

    The entity concept allows a single user to track multiple separate moving
    entities, each of which can have one or more devices attached.
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="ent"),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # vehicle, pet, person, tracker, asset
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_icon: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict | None] = mapped_column(JSON, name="metadata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="entities")
    devices: Mapped[list[Device]] = relationship(back_populates="entity", cascade="all,delete-orphan")


class Device(Base):
    """A physical GPS tracker owned by a user and attached to an Entity.

    The ``imei`` field (or equivalent device identifier) is the credential
    the ingest server trusts, so it MUST NOT be exposed through public
    (share) endpoints. Revocation is soft — set ``revoked_at`` and the
    device is ignored from then on.
    """

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="dev"),
    )
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    imei: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # set when device decommissioned; ingest rejects pings, API hides from listing
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # last successful ingest write; updated by ingest server
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    entity: Mapped[Entity] = relationship(back_populates="devices")
    positions: Mapped[list[Position]] = relationship(back_populates="device", cascade="all,delete-orphan")

    __table_args__ = (
        # Names must be unique per entity. Different entities may reuse the same
        # name — uniqueness scoped to entity_id.
        UniqueConstraint("entity_id", "name", name="devices_entity_name_uniq"),
    )


class Position(Base):
    """A single GPS fix persisted by the ingest server.

    Rows are append-only; editing or back-filling positions is not supported
    by the API. Bulk deletion cascades through :class:`Device`.
    """

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    time_id: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    altitude: Mapped[float | None] = mapped_column(Float)
    speed: Mapped[float | None] = mapped_column(Float)  # km/h
    satellites: Mapped[int | None] = mapped_column(Integer)
    is_filtered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))

    device: Mapped[Device] = relationship(back_populates="positions")

    # Composite index covers the canonical "window for one device" query;
    # also serves device_id-only lookups, so no need for a separate single-col idx.
    __table_args__ = (
        Index("ix_positions_device_time_id", "device_id", "time_id"),
        CheckConstraint("lat BETWEEN -90 AND 90", name="positions_lat_range"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="positions_lon_range"),
    )


# Junction: many-to-many between places and trips. A place can belong to any
# number of trips and vice-versa. Both FKs cascade-delete so removing either
# side cleans up the link automatically.
place_trips = Table(
    "place_trips",
    Base.metadata,
    Column("place_id", Integer, ForeignKey("places.id", ondelete="CASCADE"), nullable=False),
    Column("trip_id", Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("place_id", "trip_id", name="place_trips_pk"),
    Index("ix_place_trips_trip", "trip_id"),
)


# Junction: many-to-many between share links and places. A share link can
# include any subset of places from its trip. Cascade-delete on both sides.
share_link_places = Table(
    "share_link_places",
    Base.metadata,
    Column("share_link_id", Integer, ForeignKey("share_links.id", ondelete="CASCADE"), nullable=False),
    Column("place_id", Integer, ForeignKey("places.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("share_link_id", "place_id", name="share_link_places_pk"),
    Index("ix_share_link_places_link", "share_link_id"),
)


class Place(Base):
    """User-marked POI (favorite spot, attraction, etc.)."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="plc"),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    place_category: Mapped[str] = mapped_column(String(40), nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    # Many-to-many. Edited from the place side (`PUT /places/{id}` sends
    # `trip_ids`). The Trip side exposes the inverse for symmetry.
    trips: Mapped[list[Trip]] = relationship(
        "Trip",
        secondary=place_trips,
        back_populates="places",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="places_lat_range"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="places_lon_range"),
    )


class PlaceMedia(Base):
    """Media (image/video) attached to a place."""

    __tablename__ = "place_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="med"),
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename_original: Mapped[str] = mapped_column(String(255), nullable=False)
    filename_stored: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (CheckConstraint("media_type IN ('image', 'video', 'audio')", name="place_media_type_check"),)


# Junction: many-to-many between share links and overnight spots. A share link can
# include any subset of overnight spots from its trip. Cascade-delete on both sides.
share_link_overnight_spots = Table(
    "share_link_overnight_spots",
    Base.metadata,
    Column("share_link_id", Integer, ForeignKey("share_links.id", ondelete="CASCADE"), nullable=False),
    Column("overnight_spot_id", Integer, ForeignKey("overnight_spots.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("share_link_id", "overnight_spot_id", name="share_link_overnight_spots_pk"),
    Index("ix_share_link_overnight_spots_link", "share_link_id"),
)


class OvernightSpotMedia(Base):
    """Media (image/video) attached to an overnight spot."""

    __tablename__ = "overnight_spot_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="med"),
    )
    overnight_spot_id: Mapped[int] = mapped_column(
        ForeignKey("overnight_spots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename_original: Mapped[str] = mapped_column(String(255), nullable=False)
    filename_stored: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("media_type IN ('image', 'video', 'audio')", name="overnight_spot_media_type_check"),
    )

    overnight_spot: Mapped[OvernightSpot] = relationship(back_populates="media")


class Trip(Base):
    """User-created trip. A named time window over a device's positions.

    Owner derived through device.user_id. Stats (distance, mean speed, etc.)
    are computed on-demand from positions rather than stored, so edits to the
    window stay consistent.
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="trp"),
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4000))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Nullable: ``None`` means the trip is ongoing. Effective end is "now"
    # for stats / positions queries (see api/routers/trips.py).
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Timestamp when overnight detection was last run for this trip
    overnights_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last position timestamp included in overnight detection.
    # ``None`` means detection has never scanned this trip.
    overnights_last_checked_position_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    places: Mapped[list[Place]] = relationship(
        "Place",
        secondary=place_trips,
        back_populates="trips",
        lazy="selectin",
    )
    overnight_spots: Mapped[list[OvernightSpot]] = relationship(
        back_populates="trip",
        cascade="all,delete-orphan",
    )

    __table_args__ = (
        Index("ix_trips_device_started", "device_id", "started_at"),
        # Partial unique index: at most one ongoing trip per device.
        Index(
            "ux_trips_one_ongoing_per_device",
            "device_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at > started_at",
            name="trips_window",
        ),
    )


class ShareLink(Base):
    """Public share link for a trip with privacy filters.

    Each link has a unique token for the public URL (/share/:token). Users can
    create multiple links per trip with different privacy settings (e.g., one
    detailed link for family, one blurred link for public sharing).

    Privacy controls:
    - Time range: optionally restrict to subset of trip
    - Delay: exclude last N hours of data (default 72h = 3 days)
    - Blur: degrade coordinate precision (0=original, 100m, 500m)
    - Places: optionally include selected places from trip
    - Active/paused: toggle public accessibility without deleting config
    """

    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id(prefix="shl"),
    )
    # SHA-256(pepper:token) digest for public access (/share/:token). Separate
    # from public_id to avoid exposing internal IDs in URLs.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)

    # User-facing metadata
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))

    # Time range override (null = use trip's full started_at/ended_at window)
    share_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    share_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Delay in hours: exclude last N hours of data (default 72 = 3 days for privacy)
    delay_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)

    # Coordinate degradation in meters (0=original precision, 100, 500)
    blur_meters: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Active (publicly accessible) vs paused (configured but returns 404)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))

    # Password protection (nullable)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    trip: Mapped[Trip] = relationship("Trip")

    # Selected places to include in share (empty = no places shared)
    selected_places: Mapped[list[Place]] = relationship(
        "Place",
        secondary=share_link_places,
        lazy="selectin",
    )

    # Selected overnight spots to include in share (empty = no overnight spots shared)
    selected_overnight_spots: Mapped[list[OvernightSpot]] = relationship(
        "OvernightSpot",
        secondary=share_link_overnight_spots,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_share_links_user", "user_id"),
        Index("ix_share_links_trip", "trip_id"),
        CheckConstraint("delay_hours >= 0", name="share_links_delay_nonneg"),
        CheckConstraint("blur_meters >= 0", name="share_links_blur_nonneg"),
        CheckConstraint(
            "share_ended_at IS NULL OR share_ended_at > share_started_at",
            name="share_links_time_window",
        ),
    )


class OvernightSpot(Base):
    """Auto-detected overnight stay. Separate from user-created Places.

    Each spot belongs to a single trip and tracks the number of consecutive
    nights stayed at that location (within 80m radius).
    """

    __tablename__ = "overnight_spots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: gen_public_id("ovs"),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    nights_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # The end timestamp of the most recent night at this spot. Used for delay filtering for shared links.
    last_stay_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    trip: Mapped[Trip] = relationship(back_populates="overnight_spots")
    media: Mapped[list[OvernightSpotMedia]] = relationship(back_populates="overnight_spot", cascade="all,delete-orphan")

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="overnight_spots_lat_range"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="overnight_spots_lon_range"),
    )
