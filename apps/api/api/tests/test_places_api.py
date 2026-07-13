"""Places CRUD."""

from __future__ import annotations

import uuid
from datetime import UTC

import httpx
import pytest

pytestmark = pytest.mark.asyncio


def _payload(name: str = "Lake", **overrides) -> dict:
    base = {
        "name": name,
        "lon": 13.0,
        "lat": 52.0,
        "trip_ids": [],
        "notes": None,
        "place_category": "POI",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_places_crud_lifecycle(authed: httpx.AsyncClient):
    # Empty list initially.
    r = await authed.get("/places")
    assert r.status_code == 200
    assert r.json() == []

    # Create
    r = await authed.post("/places", json=_payload(place_category="Camping"))
    assert r.status_code == 200
    place = r.json()
    assert place["name"] == "Lake"
    assert place["place_category"] == "Camping"

    # Listed
    r = await authed.get("/places")
    assert len(r.json()) == 1
    assert r.json()[0]["place_category"] == "Camping"

    # Update
    r = await authed.patch(
        f"/places/{place['id']}",
        json=_payload(name="Lake Constance", place_category="Drinking Water"),
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Lake Constance"
    assert r.json()["place_category"] == "Drinking Water"

    # Delete
    r = await authed.delete(f"/places/{place['id']}")
    assert r.status_code == 204
    assert (await authed.get("/places")).json() == []


@pytest.mark.asyncio
async def test_place_validation_rejects_bad_coords(authed: httpx.AsyncClient):
    r = await authed.post("/places", json=_payload(lat=999.0))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_place_trip_links_round_trip(authed: httpx.AsyncClient, account):
    # Create two trips on the user's device.
    from datetime import datetime, timedelta

    start = datetime(2025, 6, 1, 8, tzinfo=UTC)
    end = start + timedelta(hours=1)
    base = {
        "device_id": str(account.device_pid),
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
        "description": None,
    }
    t1 = (await authed.post("/trips", json={**base, "name": "T1"})).json()
    t2 = (await authed.post("/trips", json={**base, "name": "T2"})).json()

    # Place linked to both trips.
    r = await authed.post(
        "/places",
        json=_payload(trip_ids=[t1["id"], t2["id"]]),
    )
    assert r.status_code == 200, r.text
    place = r.json()
    assert set(place["trip_ids"]) == {t1["id"], t2["id"]}

    # Inverse read: trip's places.
    r2 = await authed.get(f"/trips/{t1['id']}/places")
    assert r2.status_code == 200
    assert [p["id"] for p in r2.json()] == [place["id"]]

    # Replace links with only t2.
    r3 = await authed.patch(
        f"/places/{place['id']}",
        json=_payload(trip_ids=[t2["id"]]),
    )
    assert r3.status_code == 200
    assert r3.json()["trip_ids"] == [t2["id"]]

    # Unknown trip id -> 404.
    r4 = await authed.patch(
        f"/places/{place['id']}",
        json=_payload(trip_ids=[f"trp{uuid.uuid4()}"]),
    )
    assert r4.status_code == 404


@pytest.mark.asyncio
async def test_place_rejects_other_users_trip(
    authed: httpx.AsyncClient,
    other_authed: httpx.AsyncClient,
    account,
    other_account,
):
    # other_authed creates a trip on their own device.
    from datetime import datetime, timedelta

    start = datetime(2025, 6, 1, 8, tzinfo=UTC)
    end = start + timedelta(hours=1)
    r = await other_authed.post(
        "/trips",
        json={
            "device_id": str(other_account.device_pid),
            "name": "theirs",
            "description": None,
            "started_at": start.isoformat(),
            "ended_at": end.isoformat(),
        },
    )
    foreign_tid = r.json()["id"]
    # `authed` cannot link to it.
    r2 = await authed.post("/places", json=_payload(trip_ids=[foreign_tid]))
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_place_404_on_other_user(
    authed: httpx.AsyncClient,
    other_authed: httpx.AsyncClient,
):
    r = await authed.post("/places", json=_payload())
    pid = r.json()["id"]
    r2 = await other_authed.patch(
        f"/places/{pid}",
        json=_payload(name="hacked"),
    )
    assert r2.status_code == 404
    r3 = await other_authed.delete(f"/places/{pid}")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_place_404_on_unknown_id(authed: httpx.AsyncClient):
    r = await authed.delete(f"/places/plc{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_places_requires_auth(client: httpx.AsyncClient):
    assert (await client.get("/places")).status_code == 401
    assert (
        await client.post(
            "/places",
            json=_payload(),
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_place_delete_removes_uploaded_images(
    authed: httpx.AsyncClient,
    tmp_path,
    monkeypatch,
):
    from tracker_core.internal.appctx.config import AppConfig

    monkeypatch.setattr(AppConfig, "data_dir", str(tmp_path))

    # 1. Create a place
    r = await authed.post("/places", json=_payload())
    assert r.status_code == 200
    place = r.json()
    place_id = place["id"]

    # 2. Upload an image to the place
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    files = {"file": ("test.png", png_content, "image/png")}
    r_upload = await authed.post(f"/places/{place_id}/media", files=files)
    assert r_upload.status_code == 200

    # 3. Check if image file exists on disk
    uploaded_files = list((tmp_path / "uploads").rglob("*"))
    uploaded_files = [f for f in uploaded_files if f.is_file()]
    assert len(uploaded_files) == 1
    image_file_path = uploaded_files[0]
    assert image_file_path.exists()

    # 4. Now delete the place
    r_delete = await authed.delete(f"/places/{place_id}")
    assert r_delete.status_code == 204

    # 5. Verify the place no longer exists
    assert (await authed.get("/places")).json() == []

    # 6. Verify the image file and directory on disk is deleted
    assert not image_file_path.exists()
    place_dir = image_file_path.parent
    assert not place_dir.exists()
