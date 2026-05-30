"""Position read endpoints. Uses ORM-level inserts to seed positions, since
the API exposes no write endpoint (writes flow through the ingest TCP server).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.models import Position

from .conftest import Account


async def _seed(device_id: int, n: int = 3) -> list[datetime]:
    base = datetime.now(tz=timezone.utc) - timedelta(minutes=n)
    out: list[datetime] = []
    async with SessionLocal() as s:
        for i in range(n):
            time_id = base + timedelta(minutes=i)
            s.add(
                Position(
                    device_id=device_id,
                    time_id=time_id,
                    lon=13.0 + i * 0.001,
                    lat=52.0 + i * 0.001,
                    speed=20.0,
                ),
            )
            out.append(time_id)
        await s.commit()
    return out


async def test_latest_returns_null_when_no_positions(
    authed: httpx.AsyncClient,
    account: Account,
):
    r = await authed.get(f"/devices/{account.device_pid}/positions/latest")
    assert r.status_code == 200
    assert r.json() is None


async def test_latest_returns_most_recent(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed(account.device_id, n=3)
    r = await authed.get(f"/devices/{account.device_pid}/positions/latest")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert body["lat"] >= 52.0


async def test_history_returns_chronological(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed(account.device_id, n=4)
    r = await authed.get(f"/devices/{account.device_pid}/positions")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 4
    # ascending by time_id
    assert rows == sorted(rows, key=lambda p: p["time_id"])


async def test_history_respects_limit(
    authed: httpx.AsyncClient,
    account: Account,
):
    await _seed(account.device_id, n=5)
    r = await authed.get(f"/devices/{account.device_pid}/positions?limit=2")
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_history_respects_window(
    authed: httpx.AsyncClient,
    account: Account,
):
    times = await _seed(account.device_id, n=4)
    cutoff = times[2].isoformat()
    # Use httpx ``params=`` so the timestamp's ``+00:00`` is URL-encoded.
    r = await authed.get(
        f"/devices/{account.device_pid}/positions",
        params={"from": cutoff},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    # Only positions with time_id >= times[2] are returned (>=, inclusive).
    assert all(p["time_id"] >= cutoff for p in rows)
    assert len(rows) >= 1


async def test_positions_404_on_other_users_device(
    other_authed: httpx.AsyncClient,
    account: Account,
):
    r = await other_authed.get(f"/devices/{account.device_pid}/positions/latest")
    assert r.status_code == 404


async def test_positions_404_on_unknown_device(authed: httpx.AsyncClient):
    bogus = f"dev{uuid.uuid4()}"
    r = await authed.get(f"/devices/{bogus}/positions/latest")
    assert r.status_code == 404


async def test_positions_requires_auth(client: httpx.AsyncClient, account: Account):
    r = await client.get(f"/devices/{account.device_pid}/positions/latest")
    assert r.status_code == 401
