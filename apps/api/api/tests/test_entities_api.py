from __future__ import annotations

import pytest
import httpx


@pytest.mark.asyncio
async def test_entities_listing(authed: httpx.AsyncClient):
    """GET /entities returns the user's entities and attached devices."""
    r = await authed.get("/entities")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    ent = data[0]
    assert ent["name"] == "Campervan"
    assert ent["type"] == "vehicle"
    assert len(ent["devices"]) == 1
    dev = ent["devices"][0]
    assert dev["name"].startswith("Camper-")


@pytest.mark.asyncio
async def test_entities_details_and_foreign_404(
    authed: httpx.AsyncClient, other_authed: httpx.AsyncClient
):
    """GET /entities/{id} retrieves the entity; foreign users get 404."""
    r = await authed.get("/entities")
    assert r.status_code == 200
    ent_pid = r.json()[0]["id"]

    # Own retrieve
    r2 = await authed.get(f"/entities/{ent_pid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Campervan"

    # Foreign retrieve
    r3 = await other_authed.get(f"/entities/{ent_pid}")
    assert r3.status_code == 404
