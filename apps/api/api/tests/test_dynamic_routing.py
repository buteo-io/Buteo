"""Integration tests for runtime dynamic database routing (Phase 6)."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from tracker_core.store.models import Position
from tracker_core.store.tenant_db_manager import tenant_db_manager

from .conftest import Account


async def test_dynamic_routing_end_to_end(
    client: httpx.AsyncClient,
    account: Account,
    other_account: Account,
    osmand_client: httpx.AsyncClient,
) -> None:
    """Verify tenant isolation and dynamic routing on API and ingest paths."""
    from api.tests.conftest import _do_login

    # 1. Authenticate Client as Tenant A (account)
    await _do_login(client, account.email, account.password)

    # 2. Query Tenant A's trips -> should be empty but succeed (200)
    response = await client.get("/trips")
    assert response.status_code == 200, response.text
    trips = response.json()
    assert len(trips) == 0

    # 3. Authenticate another Client as Tenant B (other_account)
    other_client = httpx.AsyncClient(
        transport=client._transport, base_url="http://test"
    )
    async with other_client as oc:
        await _do_login(oc, other_account.email, other_account.password)

        # Query Tenant B's trips -> should be empty too
        res = await oc.get("/trips")
        assert res.status_code == 200
        assert len(res.json()) == 0

        # Create a trip in Tenant B's database
        trip_res = await oc.post(
            "/trips",
            json={
                "device_id": str(other_account.device_pid),
                "name": "Trip on Tenant B",
                "started_at": "2026-05-21T12:00:00Z",
            },
        )
        assert trip_res.status_code == 200, trip_res.text

        # Query Tenant B's trips -> should have 1 trip
        res = await oc.get("/trips")
        assert len(res.json()) == 1
        assert res.json()[0]["name"] == "Trip on Tenant B"

    # 4. Query Tenant A's trips again -> MUST still be empty (complete DB isolation!)
    response = await client.get("/trips")
    assert response.status_code == 200
    assert len(response.json()) == 0

    # 5. Create a trip in Tenant A's database
    trip_res_a = await client.post(
        "/trips",
        json={
            "device_id": str(account.device_pid),
            "name": "Trip on Tenant A",
            "started_at": "2026-05-21T12:00:00Z",
        },
    )
    assert trip_res_a.status_code == 200, trip_res_a.text

    # 6. Ingest a coordinate for IMEI A (Tenant A) via OsmAnd ingest Client
    import time

    now_ts = int(time.time())
    ingest_res = await osmand_client.get(
        "/traccar_client",
        params={
            "id": account.device_imei,
            "lat": "45.1234",
            "lon": "12.5678",
            "timestamp": str(now_ts),
        },
    )
    assert ingest_res.status_code == 200, ingest_res.text
    assert ingest_res.json() == {"ok": True}

    # 7. Check that the position is persisted in Tenant A's database
    async with tenant_db_manager.get_tenant_session(account.tenant_id) as s:
        stmt = select(Position).where(Position.device_id == account.device_id)
        result = await s.execute(stmt)
        positions_a = result.scalars().all()
        assert len(positions_a) == 1
        assert positions_a[0].lat == 45.1234
        assert positions_a[0].lon == 12.5678

    # 8. Check that the position is NOT persisted in Tenant B's database
    async with tenant_db_manager.get_tenant_session(other_account.tenant_id) as s:
        stmt = select(Position).where(Position.device_id == other_account.device_id)
        result = await s.execute(stmt)
        positions_b = result.scalars().all()
        assert len(positions_b) == 0
