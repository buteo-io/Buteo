"""Trip CRUD + stats + positions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.models import Position

from .conftest import Account


async def _seed_positions(device_id: int) -> tuple[datetime, datetime]:
    """Insert a tiny straight track 0..10min @ ~60 km/h. Returns (start, end)."""
    start = datetime(2025, 6, 1, 8, tzinfo=timezone.utc)
    async with SessionLocal() as s:
        for i in range(11):
            s.add(
                Position(
                    device_id=device_id,
                    time_id=start + timedelta(minutes=i),
                    lon=13.0 + i * 0.001,
                    lat=52.0,
                    speed=60.0,
                ),
            )
        await s.commit()
    return start, start + timedelta(minutes=10)


def _trip_payload(device_id: str, started: datetime, ended: datetime) -> dict:
    return {
        "device_id": device_id,
        "name": "Berlin loop",
        "description": "test trip",
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
    }


async def test_ongoing_trip_lifecycle(authed: httpx.AsyncClient, account: Account):
    start, _ = await _seed_positions(account.device_id)
    base = {
        "device_id": str(account.device_pid),
        "name": "Long haul",
        "description": None,
        "started_at": start.isoformat(),
    }
    # Create ongoing (no ended_at).
    r = await authed.post("/trips", json={**base, "ended_at": None})
    assert r.status_code == 200, r.text
    trip = r.json()
    assert trip["ended_at"] is None
    tid = trip["id"]

    # Stats / positions still work — upper bound is "now".
    s = (await authed.get(f"/trips/{tid}/stats")).json()
    assert s["points"] >= 10

    # A second ongoing trip on the same device → 409.
    r2 = await authed.post("/trips", json={**base, "ended_at": None, "name": "Other"})
    assert r2.status_code == 409

    # End it (default = now).
    r3 = await authed.post(f"/trips/{tid}/end")
    assert r3.status_code == 200
    assert r3.json()["ended_at"] is not None

    # Now another ongoing trip is allowed.
    r4 = await authed.post("/trips", json={**base, "ended_at": None, "name": "Next"})
    assert r4.status_code == 200

    # Ending an already-closed trip is a no-op (returns current state).
    r5 = await authed.post(f"/trips/{tid}/end")
    assert r5.status_code == 200
    assert r5.json()["ended_at"] == r3.json()["ended_at"]


async def test_trip_crud_and_stats(authed: httpx.AsyncClient, account: Account):
    start, end = await _seed_positions(account.device_id)

    # Create
    r = await authed.post(
        "/trips",
        json=_trip_payload(str(account.device_pid), start, end),
    )
    assert r.status_code == 200, r.text
    trip = r.json()
    assert trip["name"] == "Berlin loop"
    tid = trip["id"]

    # List
    r2 = await authed.get("/trips")
    assert any(t["id"] == tid for t in r2.json())

    # Stats
    r3 = await authed.get(f"/trips/{tid}/stats")
    assert r3.status_code == 200
    s = r3.json()
    assert s["points"] >= 10
    assert s["distance_km"] > 0
    assert s["duration_s"] == 600

    # Positions
    r4 = await authed.get(f"/trips/{tid}/positions")
    assert r4.status_code == 200
    assert len(r4.json()) >= 10

    # Update (rename)
    r5 = await authed.patch(
        f"/trips/{tid}",
        json=_trip_payload(str(account.device_pid), start, end) | {"name": "Renamed"},
    )
    assert r5.status_code == 200
    assert r5.json()["name"] == "Renamed"

    # Delete
    r6 = await authed.delete(f"/trips/{tid}")
    assert r6.status_code == 204


async def test_trip_patch_is_partial(authed: httpx.AsyncClient, account: Account):
    """PATCH should only touch the fields explicitly present in the body."""
    start, end = await _seed_positions(account.device_id)
    created = (
        await authed.post(
            "/trips",
            json=_trip_payload(str(account.device_pid), start, end),
        )
    ).json()
    tid = created["id"]
    # Rename only — start/end/description must stay.
    r = await authed.patch(f"/trips/{tid}", json={"name": "Just rename"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Just rename"
    assert body["description"] == created["description"]
    assert body["started_at"] == created["started_at"]
    assert body["ended_at"] == created["ended_at"]
    # Reopen via explicit null ended_at.
    r2 = await authed.patch(f"/trips/{tid}", json={"ended_at": None})
    assert r2.status_code == 200
    assert r2.json()["ended_at"] is None


async def test_trip_patch_rejects_unknown_keys(
    authed: httpx.AsyncClient,
    account: Account,
):
    start, end = await _seed_positions(account.device_id)
    tid = (
        await authed.post(
            "/trips",
            json=_trip_payload(str(account.device_pid), start, end),
        )
    ).json()["id"]
    r = await authed.patch(f"/trips/{tid}", json={"hacker": "yes"})
    assert r.status_code == 422


async def test_trip_400_when_window_inverted(
    authed: httpx.AsyncClient,
    account: Account,
):
    start = datetime.now(tz=timezone.utc)
    end = start - timedelta(minutes=1)
    r = await authed.post(
        "/trips",
        json=_trip_payload(str(account.device_pid), start, end),
    )
    assert r.status_code == 400


async def test_trip_404_when_device_not_owned(
    other_authed: httpx.AsyncClient,
    account: Account,
):
    start = datetime(2025, 6, 1, 8, tzinfo=timezone.utc)
    end = start + timedelta(minutes=5)
    r = await other_authed.post(
        "/trips",
        json=_trip_payload(str(account.device_pid), start, end),
    )
    assert r.status_code == 404


async def test_trip_404_on_unknown_id(authed: httpx.AsyncClient):
    r = await authed.get(f"/trips/trp{uuid.uuid4()}/stats")
    assert r.status_code == 404


async def test_trip_isolation(
    authed: httpx.AsyncClient,
    other_authed: httpx.AsyncClient,
    account: Account,
):
    start = datetime(2025, 6, 1, 8, tzinfo=timezone.utc)
    end = start + timedelta(minutes=5)
    r = await authed.post(
        "/trips",
        json=_trip_payload(str(account.device_pid), start, end),
    )
    tid = r.json()["id"]
    r2 = await other_authed.delete(f"/trips/{tid}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_trip_deletion_cleans_media_files(
    authed: httpx.AsyncClient,
    account: Account,
    tmp_path,
    monkeypatch,
):
    from sqlalchemy import select
    from tracker_core.internal.appctx.config import AppConfig
    from tracker_core.store.models import OvernightSpot
    from tracker_core.store.models import Trip as TripModel

    monkeypatch.setattr(AppConfig, "data_dir", str(tmp_path))

    start = datetime.now(timezone.utc) - timedelta(days=10)
    end = start + timedelta(hours=5)
    r = await authed.post(
        "/trips",
        json=_trip_payload(str(account.device_pid), start, end),
    )
    assert r.status_code == 200, r.text
    trip = r.json()
    trip_id = trip["id"]
    trip_public_id = trip_id

    recent_stay = datetime.now(timezone.utc) - timedelta(hours=10)
    async with SessionLocal() as s:
        trip_db = (
            await s.execute(
                select(TripModel).where(TripModel.public_id == trip_public_id)
            )
        ).scalar_one()

        spot = OvernightSpot(
            user_id=account.user_id,
            trip_id=trip_db.id,
            name="Spot to delete",
            lon=13.0,
            lat=52.0,
            nights_count=1,
            last_stay_at=recent_stay,
        )
        s.add(spot)
        await s.commit()
        await s.refresh(spot)
        spot_public_id = spot.public_id

    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    files = {"file": ("recent.png", png_content, "image/png")}
    r_upload = await authed.post(
        f"/overnight-spots/{spot_public_id}/media", files=files
    )
    assert r_upload.status_code == 200, r_upload.text

    media_dir = tmp_path / "uploads" / str(account.user_id) / str(spot_public_id)
    assert media_dir.exists()
    assert media_dir.is_dir()
    assert list(media_dir.glob("*"))

    r_delete = await authed.delete(f"/trips/{trip_id}")
    assert r_delete.status_code == 204

    assert not media_dir.exists()

    async with SessionLocal() as s:
        spot_in_db = (
            await s.execute(
                select(OvernightSpot).where(OvernightSpot.public_id == spot_public_id)
            )
        ).scalar_one_or_none()
        assert spot_in_db is None


@pytest.mark.asyncio
async def test_trip_gpx_export(authed: httpx.AsyncClient, account: Account):
    # Seed position with full tracker data
    start = datetime(2025, 6, 1, 8, tzinfo=timezone.utc)
    async with SessionLocal() as s:
        s.add(
            Position(
                device_id=account.device_id,
                time_id=start,
                lon=13.0,
                lat=52.0,
                speed=36.0,  # 36 km/h = 10 m/s
                altitude=450.0,
                satellites=12,
            )
        )
        await s.commit()

    # Create a trip
    r = await authed.post(
        "/trips",
        json=_trip_payload(
            str(account.device_pid), start, start + timedelta(minutes=5)
        ),
    )
    assert r.status_code == 200
    trip_id = r.json()["id"]

    # Export WITH metadata (default - though now simplified to not include extra tags)
    r_meta = await authed.get(f"/trips/{trip_id}/export.gpx")
    assert r_meta.status_code == 200
    gpx_meta = r_meta.text
    assert "<time>" in gpx_meta
    assert "<ele>" not in gpx_meta
    assert "<sat>" not in gpx_meta
    assert "<speed>" not in gpx_meta

    # Export WITHOUT metadata
    r_no_meta = await authed.get(f"/trips/{trip_id}/export.gpx?include_metadata=false")
    assert r_no_meta.status_code == 200
    gpx_no_meta = r_no_meta.text
    assert "<time>" in gpx_no_meta
    assert "<ele>" not in gpx_no_meta
    assert "<sat>" not in gpx_no_meta
    assert "<speed>" not in gpx_no_meta

    # Export as CSV
    r_csv = await authed.get(f"/trips/{trip_id}/export.csv")
    assert r_csv.status_code == 200
    csv_text = r_csv.text
    assert "time_id,lat,lon,altitude,speed_kmh,satellites" in csv_text
    assert "52.0,13.0" in csv_text
    assert "450.0" in csv_text


async def _seed_trip(device_id: int) -> str:
    """Insert a trip directly into the DB and return its public_id."""
    from tracker_core.store.models import Trip

    start = datetime(2025, 7, 1, 8, tzinfo=timezone.utc)
    ended = start + timedelta(hours=3)
    async with SessionLocal() as s:
        t = Trip(
            device_id=device_id,
            name="Pre-seeded trip",
            started_at=start,
            ended_at=ended,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return str(t.public_id)


async def test_read_only_account_blocked_from_mutations(
    read_only_authed: httpx.AsyncClient, account: Account
):
    """read_only feature flag → 403 on every mutating endpoint; reads still work.

    The trip is seeded via direct DB insert (before the read_only flag is applied
    by the fixture) so we never need an authenticated writable HTTP client here.
    """
    trip_id = await _seed_trip(account.device_id)
    c = read_only_authed

    start = datetime(2025, 6, 1, 8, tzinfo=timezone.utc)
    ended = start + timedelta(hours=2)
    trip_payload = {
        "device_id": str(account.device_pid),
        "name": "Demo trip",
        "started_at": start.isoformat(),
        "ended_at": ended.isoformat(),
    }

    # --- trips: writes blocked, reads allowed ---
    r = await c.post("/trips", json=trip_payload)
    assert r.status_code == 403, r.text

    r = await c.patch(f"/trips/{trip_id}", json={"name": "Renamed"})
    assert r.status_code == 403

    r = await c.post(f"/trips/{trip_id}/end")
    assert r.status_code == 403

    r = await c.delete(f"/trips/{trip_id}")
    assert r.status_code == 403

    r = await c.get("/trips")
    assert r.status_code == 200

    # --- places: writes blocked, reads allowed ---
    place_payload = {
        "name": "Camp spot",
        "lon": 13.4,
        "lat": 52.5,
        "place_category": "Camping",
        "trip_ids": [],
    }
    r = await c.post("/places", json=place_payload)
    assert r.status_code == 403

    r = await c.get("/places")
    assert r.status_code == 200

    # --- overnight spots: detect is automatic (not user-initiated write), allowed ---
    r = await c.post(f"/trips/{trip_id}/overnight-spots/detect")
    assert r.status_code == 200

    r = await c.get(f"/trips/{trip_id}/overnight-spots")
    assert r.status_code == 200

    # --- share links: writes blocked, reads allowed ---
    r = await c.post("/share-links", json={"trip_id": trip_id, "name": "Public share"})
    assert r.status_code == 403

    r = await c.get("/share-links")
    assert r.status_code == 200
