"""Traccar Client + OwnTracks HTTP ingest endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import delete, select, update
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.models import Device, Position

from .conftest import Account


async def _positions(device_id: int) -> list[Position]:
    async with SessionLocal() as s:
        rows = (
            await s.scalars(
                select(Position)
                .where(Position.device_id == device_id, Position.is_filtered.is_(False))
                .order_by(Position.time_id),
            )
        ).all()
        # Detach so the caller can read attrs after the session closes.
        for r in rows:
            s.expunge(r)
        return list(rows)


async def _wipe_positions(device_id: int) -> None:
    async with SessionLocal() as s:
        await s.execute(delete(Position).where(Position.device_id == device_id))
        await s.commit()


async def test_osmand_get_persists_fix(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    await _wipe_positions(account.device_id)
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.5",
            "lon": "13.4",
            "timestamp": "1700000000",
            "speed": "10",  # knots
            "bearing": "90",
            "altitude": "42",
        },
    )
    assert r.status_code == 200, r.text
    rows = await _positions(account.device_id)
    assert len(rows) == 1
    p = rows[0]
    assert p.lat == pytest.approx(52.5)
    assert p.lon == pytest.approx(13.4)
    assert p.speed == pytest.approx(10 * 1.852)  # knots → km/h
    assert p.altitude == pytest.approx(42)
    p_time = p.time_id.replace(tzinfo=UTC) if p.time_id.tzinfo is None else p.time_id
    assert p_time == datetime.fromtimestamp(1700000000, tz=UTC)


async def test_owntracks_location_persists_fix(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    await _wipe_positions(account.device_id)
    r = await osmand_client.post(
        "/owntracks",
        headers={"X-Limit-D": account.device_imei},
        json={"_type": "location", "lat": 10.0, "lon": 20.0, "tst": 1700000000},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
    rows = await _positions(account.device_id)
    assert len(rows) == 1
    assert rows[0].lat == pytest.approx(10.0)
    assert rows[0].lon == pytest.approx(20.0)


async def test_osmand_post_form_body(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    await _wipe_positions(account.device_id)
    r = await osmand_client.post(
        "/traccar_client",
        data={"id": account.device_imei, "lat": "1.0", "lon": "2.0"},
    )
    assert r.status_code == 200, r.text
    rows = await _positions(account.device_id)
    assert len(rows) == 1
    assert rows[0].lat == pytest.approx(1.0)


async def test_osmand_post_query_params(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """IOS Traccar Client style: POST with everything in the URL."""
    await _wipe_positions(account.device_id)
    r = await osmand_client.post(
        f"/traccar_client?id={account.device_imei}&lat=1.5&lon=2.5",
    )
    assert r.status_code == 200, r.text
    rows = await _positions(account.device_id)
    assert len(rows) == 1


async def test_osmand_iso_timestamp(osmand_client: httpx.AsyncClient, account: Account):
    await _wipe_positions(account.device_id)
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "0",
            "lon": "0",
            "timestamp": "2024-05-01T12:00:00Z",
        },
    )
    assert r.status_code == 200
    rows = await _positions(account.device_id)
    p_time = rows[0].time_id.replace(tzinfo=UTC) if rows[0].time_id.tzinfo is None else rows[0].time_id
    assert p_time == datetime(2024, 5, 1, 12, 0, 0, tzinfo=UTC)


async def test_osmand_unknown_device(osmand_client: httpx.AsyncClient):
    r = await osmand_client.get(
        "/traccar_client",
        params={"id": "999999999999999", "lat": "0", "lon": "0"},
    )
    assert r.status_code == 401


async def test_osmand_revoked_device(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    async with SessionLocal() as s:
        await s.execute(
            update(Device).where(Device.id == account.device_id).values(revoked_at=datetime.now(tz=UTC)),
        )
        await s.commit()
    r = await osmand_client.get(
        "/traccar_client",
        params={"id": account.device_imei, "lat": "0", "lon": "0"},
    )
    assert r.status_code == 410


async def test_osmand_missing_id(osmand_client: httpx.AsyncClient):
    r = await osmand_client.get("/traccar_client", params={"lat": "0", "lon": "0"})
    assert r.status_code == 400


async def test_osmand_missing_coords(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    r = await osmand_client.get("/traccar_client", params={"id": account.device_imei})
    assert r.status_code == 400


async def test_osmand_rejects_pre_2020_timestamp(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """Phone with a busted clock posting `timestamp=0` must be rejected.

    Without the bound the row would land at 1970-01-01 and forever sit at
    the top of every chart.
    """
    r = await osmand_client.get(
        "/traccar_client",
        params={"id": account.device_imei, "lat": "0", "lon": "0", "timestamp": "0"},
    )
    assert r.status_code == 400
    assert "timestamp" in r.json()["detail"].lower()


async def test_osmand_rejects_far_future_timestamp(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "0",
            "lon": "0",
            "timestamp": "2099-01-01T00:00:00Z",
        },
    )
    assert r.status_code == 400


async def test_osmand_out_of_range(osmand_client: httpx.AsyncClient, account: Account):
    r = await osmand_client.get(
        "/traccar_client",
        params={"id": account.device_imei, "lat": "100", "lon": "0"},
    )
    assert r.status_code == 400


async def test_osmand_updates_last_seen(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    await _wipe_positions(account.device_id)
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "0",
            "lon": "0",
            "timestamp": "1700000000",
        },
    )
    assert r.status_code == 200
    async with SessionLocal() as s:
        d = await s.get(Device, account.device_id)
        d_last_seen = d.last_seen_at.replace(tzinfo=UTC) if d.last_seen_at.tzinfo is None else d.last_seen_at
        assert d_last_seen == datetime.fromtimestamp(1700000000, tz=UTC)


async def test_owntracks_ignores_non_location_payload(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    await _wipe_positions(account.device_id)
    r = await osmand_client.post(
        "/owntracks",
        headers={"X-Limit-D": account.device_imei},
        json={"_type": "transition", "event": "enter"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
    rows = await _positions(account.device_id)
    assert rows == []


async def test_owntracks_empty_payload_ignored(osmand_client: httpx.AsyncClient):
    r = await osmand_client.post(
        "/owntracks",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []


async def test_spike_filter_removes_isolated_out_and_back(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """A-B-C out-and-back within short gaps => B removed."""
    await _wipe_positions(account.device_id)

    # A: Berlin center
    ts_a = 1700000000
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.52",
            "lon": "13.405",
            "timestamp": str(ts_a),
        },
    )
    assert r.status_code == 200

    # B: ~17km away (spike out)
    ts_b = ts_a + 600  # 10 min later
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.67",
            "lon": "13.55",
            "timestamp": str(ts_b),
        },
    )
    assert r.status_code == 200

    # C: back near A (~1km from A)
    ts_c = ts_b + 600  # 10 min later
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.53",
            "lon": "13.41",
            "timestamp": str(ts_c),
        },
    )
    assert r.status_code == 200

    rows = await _positions(account.device_id)
    # Should have A and C, but NOT B (spike filtered)
    assert len(rows) == 2, f"Expected 2 positions (A,C), got {len(rows)}: {[r.time_id for r in rows]}"
    times = {r.time_id.replace(tzinfo=UTC) if r.time_id.tzinfo is None else r.time_id for r in rows}
    dt_a = datetime.fromtimestamp(ts_a, tz=UTC)
    dt_b = datetime.fromtimestamp(ts_b, tz=UTC)
    dt_c = datetime.fromtimestamp(ts_c, tz=UTC)
    assert dt_a in times, f"A (ts={ts_a}) should be present, got times: {times}"
    assert dt_c in times, f"C (ts={ts_c}) should be present, got times: {times}"
    assert dt_b not in times, f"B (ts={ts_b}) should be filtered out, got times: {times}"


async def test_spike_filter_keeps_continuous_travel(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """High-speed continuous travel (no return near start) => keep all."""
    await _wipe_positions(account.device_id)

    # A: Berlin
    ts_a = 1700000000
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.52",
            "lon": "13.405",
            "timestamp": str(ts_a),
        },
    )
    assert r.status_code == 200

    # B: ~17km away
    ts_b = ts_a + 600
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.67",
            "lon": "13.55",
            "timestamp": str(ts_b),
        },
    )
    assert r.status_code == 200

    # C: another ~17km away (continuing in same direction, not returning)
    ts_c = ts_b + 600
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.82",
            "lon": "13.70",
            "timestamp": str(ts_c),
        },
    )
    assert r.status_code == 200

    rows = await _positions(account.device_id)
    # All three should be kept (continuous travel, not a spike)
    assert len(rows) == 3, f"Expected 3 positions, got {len(rows)}"


async def test_spike_filter_keeps_long_gap(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """Return-near-start but long gap (>15 min) => keep all."""
    await _wipe_positions(account.device_id)

    # A: Berlin
    ts_a = 1700000000
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.52",
            "lon": "13.405",
            "timestamp": str(ts_a),
        },
    )
    assert r.status_code == 200

    # B: ~17km away
    ts_b = ts_a + 600
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.67",
            "lon": "13.55",
            "timestamp": str(ts_b),
        },
    )
    assert r.status_code == 200

    # C: back near A but with LONG gap (>15 min)
    ts_c = ts_b + 1200  # 20 min later
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.53",
            "lon": "13.41",
            "timestamp": str(ts_c),
        },
    )
    assert r.status_code == 200

    rows = await _positions(account.device_id)
    # All three should be kept (gap too long to be a spike)
    assert len(rows) == 3, f"Expected 3 positions, got {len(rows)}"


async def test_spike_filter_cross_request_removes_persisted_spike(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """Cross-request: A+B in request 1, C in request 2 => persisted B removed."""
    await _wipe_positions(account.device_id)

    # Request 1: A and B (spike pattern start)
    ts_a = 1700000000
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.52",
            "lon": "13.405",
            "timestamp": str(ts_a),
        },
    )
    assert r.status_code == 200

    ts_b = ts_a + 600
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.67",
            "lon": "13.55",
            "timestamp": str(ts_b),
        },
    )
    assert r.status_code == 200

    # Verify A and B are stored
    rows = await _positions(account.device_id)
    assert len(rows) == 2

    # Request 2: C (completes the spike pattern, should trigger B removal)
    ts_c = ts_b + 600
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.53",
            "lon": "13.41",
            "timestamp": str(ts_c),
        },
    )
    assert r.status_code == 200

    rows = await _positions(account.device_id)
    # Should have A and C, but NOT B (persisted spike removed)
    assert len(rows) == 2, f"Expected 2 positions after cross-request filter, got {len(rows)}"


async def test_spike_filter_ignores_out_of_order_timestamp(
    osmand_client: httpx.AsyncClient,
    account: Account,
):
    """Out-of-order C timestamp must not trigger persisted B deletion."""
    await _wipe_positions(account.device_id)

    ts_a = 1700000000
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.52",
            "lon": "13.405",
            "timestamp": str(ts_a),
        },
    )
    assert r.status_code == 200

    ts_b = ts_a + 600
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.67",
            "lon": "13.55",
            "timestamp": str(ts_b),
        },
    )
    assert r.status_code == 200

    # C is out-of-order (older than B). Without guard, this could classify as spike.
    ts_c = ts_b - 300
    r = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "52.53",
            "lon": "13.41",
            "timestamp": str(ts_c),
        },
    )
    assert r.status_code == 200

    rows = await _positions(account.device_id)
    assert len(rows) == 3, f"Expected 3 positions (no spike deletion), got {len(rows)}"
