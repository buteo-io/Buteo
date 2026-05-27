"""initial consolidated schema

All tables in one revision. Includes Entity concept, user-entity-device hierarchy, and all core tracker tables.

Revision ID: 0001
Revises:
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def _public_id_col() -> sa.Column:
    return sa.Column(
        "public_id",
        sa.String(40),
        nullable=False,
        unique=True,
    )


def upgrade() -> None:
    # 1. Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("token_version", sa.Integer, nullable=False, server_default=sa.text("0")),
        *_ts_cols(),
        sa.CheckConstraint("email = lower(email)", name="users_email_lowercase"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_public_id", "users", ["public_id"], unique=True)

    # 2. Entities
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("avatar_icon", sa.String(120), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        *_ts_cols(),
    )
    op.create_index("ix_entities_user_id", "entities", ["user_id"])
    op.create_index("ix_entities_public_id", "entities", ["public_id"], unique=True)

    # 4. Devices
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column(
            "entity_id",
            sa.Integer,
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("imei", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        *_ts_cols(),
        sa.UniqueConstraint("entity_id", "name", name="devices_entity_name_uniq"),
    )
    op.create_index("ix_devices_entity_id", "devices", ["entity_id"])
    op.create_index("ix_devices_imei", "devices", ["imei"], unique=True)
    op.create_index("ix_devices_public_id", "devices", ["public_id"], unique=True)

    # 5. Positions
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("time_id", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("altitude", sa.Float),
        sa.Column("speed", sa.Float),
        sa.Column("satellites", sa.Integer),
        sa.Column("is_filtered", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name="positions_lat_range"),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name="positions_lon_range"),
    )
    op.create_index("ix_positions_device_time_id", "positions", ["device_id", "time_id"])

    # 6. Places
    op.create_table(
        "places",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.String(2000)),
        sa.Column("place_category", sa.String(40), nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        *_ts_cols(),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name="places_lat_range"),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name="places_lon_range"),
    )
    op.create_index("ix_places_user_id", "places", ["user_id"])
    op.create_index("ix_places_public_id", "places", ["public_id"], unique=True)

    # 7. Alarms
    op.create_table(
        "alarms",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column(
            "device_id",
            sa.Integer,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("armed", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("name", sa.String(120), nullable=False, server_default=sa.text("'Alarm'")),
        sa.Column("lon", sa.Float),
        sa.Column("lat", sa.Float),
        sa.Column("radius_m", sa.Float),
        sa.Column("speed_kmh", sa.Float),
        sa.Column("max_silence_s", sa.Integer),
        *_ts_cols(),
        sa.CheckConstraint("kind IN ('geofence_exit','motion','power')", name="alarms_kind_chk"),
    )
    op.create_index("ix_alarms_device_id", "alarms", ["device_id"])
    op.create_index("ix_alarms_public_id", "alarms", ["public_id"], unique=True)

    # 8. Trips
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column(
            "device_id",
            sa.Integer,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(4000)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overnights_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overnights_last_checked_position_time", sa.DateTime(timezone=True), nullable=True),
        *_ts_cols(),
        sa.CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="trips_window"),
    )
    op.create_index("ix_trips_device_id", "trips", ["device_id"])
    op.create_index("ix_trips_public_id", "trips", ["public_id"], unique=True)
    op.create_index("ix_trips_device_started", "trips", ["device_id", "started_at"])
    op.create_index(
        "ux_trips_one_ongoing_per_device",
        "trips",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )

    # 9. Place Trips
    op.create_table(
        "place_trips",
        sa.Column(
            "place_id",
            sa.Integer,
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trip_id",
            sa.Integer,
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("place_id", "trip_id", name="place_trips_pk"),
    )
    op.create_index("ix_place_trips_trip", "place_trips", ["trip_id"])

    # 10. Alarm Events
    op.create_table(
        "alarm_events",
        sa.Column("id", sa.Integer, primary_key=True),
        _public_id_col(),
        sa.Column(
            "alarm_id",
            sa.Integer,
            sa.ForeignKey("alarms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.Integer,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("lon", sa.Float),
        sa.Column("lat", sa.Float),
        sa.Column("detail", sa.String(500)),
        sa.Column(
            "acknowledged",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index("ix_alarm_events_alarm_id", "alarm_events", ["alarm_id"])
    op.create_index("ix_alarm_events_device_ts", "alarm_events", ["device_id", "ts"])
    op.create_index("ix_alarm_events_public_id", "alarm_events", ["public_id"], unique=True)

    # 11. Share Links
    op.create_table(
        "share_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(40), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("share_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("share_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delay_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blur_meters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("blur_meters >= 0", name="share_links_blur_nonneg"),
        sa.CheckConstraint("delay_hours >= 0", name="share_links_delay_nonneg"),
        sa.CheckConstraint(
            "share_ended_at IS NULL OR share_ended_at > share_started_at", name="share_links_time_window"
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_share_links_public_id", "share_links", ["public_id"], unique=True)
    op.create_index("ix_share_links_token", "share_links", ["token"], unique=True)
    op.create_index("ix_share_links_trip", "share_links", ["trip_id"])
    op.create_index("ix_share_links_user", "share_links", ["user_id"])

    # 12. Share Link Places
    op.create_table(
        "share_link_places",
        sa.Column("share_link_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["share_link_id"], ["share_links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("share_link_id", "place_id", name="share_link_places_pk"),
    )
    op.create_index("ix_share_link_places_link", "share_link_places", ["share_link_id"])

    # 13. Overnight Spots
    op.create_table(
        "overnight_spots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(40), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("nights_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "last_stay_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name="overnight_spots_lat_range"),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name="overnight_spots_lon_range"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_overnight_spots_public_id", "overnight_spots", ["public_id"], unique=True)
    op.create_index("ix_overnight_spots_trip", "overnight_spots", ["trip_id"])
    op.create_index("ix_overnight_spots_user", "overnight_spots", ["user_id"])

    # 14. Place Media
    op.create_table(
        "place_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(40), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename_original", sa.String(length=255), nullable=False),
        sa.Column("filename_stored", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("media_type IN ('image', 'video')", name="place_media_type_check"),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_place_media_public_id", "place_media", ["public_id"], unique=True)
    op.create_index("ix_place_media_place_id", "place_media", ["place_id"])
    op.create_index("ix_place_media_user_id", "place_media", ["user_id"])

    # 15. Overnight Spot Media
    op.create_table(
        "overnight_spot_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(40), nullable=False),
        sa.Column("overnight_spot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename_original", sa.String(length=255), nullable=False),
        sa.Column("filename_stored", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("media_type IN ('image', 'video', 'audio')", name="overnight_spot_media_type_check"),
        sa.ForeignKeyConstraint(["overnight_spot_id"], ["overnight_spots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_overnight_spot_media_overnight_spot_id", "overnight_spot_media", ["overnight_spot_id"])
    op.create_index("ix_overnight_spot_media_public_id", "overnight_spot_media", ["public_id"], unique=True)
    op.create_index("ix_overnight_spot_media_user_id", "overnight_spot_media", ["user_id"])

    # 16. Share Link Overnight Spots
    op.create_table(
        "share_link_overnight_spots",
        sa.Column("share_link_id", sa.Integer(), nullable=False),
        sa.Column("overnight_spot_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["overnight_spot_id"], ["overnight_spots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["share_link_id"], ["share_links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("share_link_id", "overnight_spot_id", name="share_link_overnight_spots_pk"),
    )
    op.create_index("ix_share_link_overnight_spots_link", "share_link_overnight_spots", ["share_link_id"])


def downgrade() -> None:
    for t in (
        "share_link_overnight_spots",
        "overnight_spot_media",
        "place_media",
        "overnight_spots",
        "share_link_places",
        "share_links",
        "alarm_events",
        "place_trips",
        "trips",
        "alarms",
        "places",
        "positions",
        "devices",
        "tags",
        "entities",
        "users",
    ):
        op.drop_table(t)
