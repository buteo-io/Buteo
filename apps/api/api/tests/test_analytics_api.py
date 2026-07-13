"""Analytics endpoints (trips, overnights, summary, mileage, exports)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.models import Position

from .conftest import Account


async def _seed_drive(device_id: int) -> tuple[datetime, datetime]:
    """Seed ~10 minutes of driving + 15 minutes stopped (so detect_trips finds one trip)."""
    base = datetime(2025, 5, 1, 9, tzinfo=UTC)
    async with SessionLocal() as s:
        for i in range(11):
            s.add(
                Position(
                    device_id=device_id,
                    time_id=base + timedelta(minutes=i),
                    lon=13.0 + i * 0.001,
                    lat=52.0,
                    speed=60.0,
                ),
            )
        for i in range(11, 26):  # 15 min stopped at end-point -> closes trip
            s.add(
                Position(
                    device_id=device_id,
                    time_id=base + timedelta(minutes=i),
                    lon=13.01,
                    lat=52.0,
                    speed=0.0,
                ),
            )
        await s.commit()
    return base, base + timedelta(minutes=25)


async def test_summary_for_owned_device(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed_drive(account.device_id)
    r = await authed.get(f"/devices/{account.device_pid}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["points"] >= 20
    assert body["distance_km"] >= 0


async def test_trips_endpoint_detects_segment(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed_drive(account.device_id)
    r = await authed.get(f"/devices/{account.device_pid}/trips")
    assert r.status_code == 200
    trips = r.json()
    assert len(trips) >= 1


async def test_mileage_buckets(authed: httpx.AsyncClient, account: Account):
    await _seed_drive(account.device_id)
    r = await authed.get(
        f"/devices/{account.device_pid}/mileage?granularity=day",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["granularity"] == "day"
    assert isinstance(body["buckets"], list)


async def test_mileage_invalid_granularity(
    authed: httpx.AsyncClient,
    account: Account,
):
    r = await authed.get(
        f"/devices/{account.device_pid}/mileage?granularity=decade",
    )
    assert r.status_code == 422


async def test_export_gpx_attachment(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed_drive(account.device_id)
    r = await authed.get(f"/devices/{account.device_pid}/export.gpx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gpx+xml")
    assert "attachment" in r.headers["content-disposition"]
    assert "<gpx" in r.text


async def test_export_csv_attachment(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed_drive(account.device_id)
    r = await authed.get(f"/devices/{account.device_pid}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("time_id,lat,lon")


async def test_analytics_404_other_user(
    other_authed: httpx.AsyncClient,
    account: Account,
):
    r = await other_authed.get(f"/devices/{account.device_pid}/summary")
    assert r.status_code == 404


async def test_analytics_404_unknown_device(authed: httpx.AsyncClient):
    r = await authed.get(f"/devices/dev{uuid.uuid4()}/trips")
    assert r.status_code == 404
