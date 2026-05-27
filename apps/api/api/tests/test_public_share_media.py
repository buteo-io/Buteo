"""Tests for public share media privacy validation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete, select
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.core_db import init_core_db
from tracker_core.store.identity_db import (
    GPSDevice,
    IdentitySessionLocal,
    Tenant,
    init_identity_db,
)
from tracker_core.store.models import Device, Entity, OvernightSpot, User
from tracker_core.store.security import hash_password
from tracker_core.store.tenant_db_manager import tenant_db_manager

from .conftest import Account, _unique_imei


async def _provision_no_underscores(
    email: str, password: str = "pw1234abcd!!"
) -> Account:
    """Create a user + device pair with no underscores in tenant_id."""
    await init_identity_db()
    tenant_id = f"tenant{uuid.uuid4().hex}"

    from pathlib import Path

    from tracker_core.internal.appctx.config import AppConfig

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
        if db_file.exists():
            try:
                db_file.unlink()
            except OSError:
                pass

    async with IdentitySessionLocal() as id_s:
        await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
        await id_s.commit()

        tenant = Tenant(
            tenant_id=tenant_id,
            email=email,
            password_hash=hash_password(password),
            database_type="sqlite",
            database_name=f"test_tenant_{tenant_id}.db",
        )
        id_s.add(tenant)
        await id_s.commit()

    tenant_url = tenant_db_manager.get_tenant_url(tenant_id)
    await init_core_db(tenant_url)

    imei = _unique_imei()
    async with tenant_db_manager.get_tenant_session(tenant_id) as s:
        u = User(email=email, password_hash=hash_password(password))
        s.add(u)
        await s.flush()
        ent = Entity(user_id=u.id, type="vehicle", name="Campervan")
        s.add(ent)
        await s.flush()
        d = Device(entity_id=ent.id, imei=imei, name=f"Camper-{imei[-4:]}")
        s.add(d)
        await s.commit()
        await s.refresh(u)
        await s.refresh(d)

    async with IdentitySessionLocal() as id_s:
        gps_device = GPSDevice(
            imei=imei,
            tenant_id=tenant_id,
        )
        id_s.add(gps_device)
        await id_s.commit()

    return Account(
        email=email,
        password=password,
        user_id=u.id,
        device_imei=imei,
        device_id=d.id,
        device_pid=d.public_id,
        tenant_id=tenant_id,
    )


async def _purge_custom(tenant_id: str) -> None:
    await tenant_db_manager.clear_cache()
    async with IdentitySessionLocal() as id_s:
        await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
        await id_s.commit()

    from pathlib import Path

    from tracker_core.internal.appctx.config import AppConfig

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
        if db_file.exists():
            try:
                db_file.unlink()
            except OSError:
                pass


@pytest.fixture
async def account() -> AsyncIterator[Account]:
    """Custom test account with no underscores in tenant_id."""
    acc = await _provision_no_underscores("alice-media@test.example")
    from tracker_core.store.tenant_db_manager import current_tenant_id

    token = current_tenant_id.set(acc.tenant_id)
    try:
        yield acc
    finally:
        current_tenant_id.reset(token)
        await _purge_custom(acc.tenant_id)


@pytest.mark.asyncio
async def test_public_share_media_privacy_bypass_fixed(
    authed: httpx.AsyncClient,
    client: httpx.AsyncClient,
    account: Account,
):
    """Verify overnight spot media is hidden if last_stay_at is in privacy window."""

    # 1. Create a trip
    start = datetime.now(timezone.utc) - timedelta(days=10)
    trip_res = await authed.post(
        "/trips",
        json={
            "device_id": str(account.device_pid),
            "name": "Media Test Trip",
            "started_at": start.isoformat(),
            "ended_at": None,
        },
    )
    assert trip_res.status_code == 200, trip_res.text
    trip = trip_res.json()
    trip_id = trip["id"]
    trip_public_id = trip["id"]

    # 2. Add an overnight spot directly in the DB
    # CASE A: Spot within the delay window (recent)
    recent_stay = datetime.now(timezone.utc) - timedelta(hours=10)
    async with SessionLocal() as s:
        from tracker_core.store.models import Trip as TripModel

        trip_db = (
            await s.execute(
                select(TripModel).where(TripModel.public_id == trip_public_id)
            )
        ).scalar_one()

        spot_recent = OvernightSpot(
            user_id=account.user_id,
            trip_id=trip_db.id,
            name="Recent Spot",
            lon=13.0,
            lat=52.0,
            nights_count=1,
            last_stay_at=recent_stay,
        )
        s.add(spot_recent)
        await s.commit()
        await s.refresh(spot_recent)
        spot_recent_public_id = spot_recent.public_id

    # 3. Upload media for this recent spot
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    files = {"file": ("recent.png", png_content, "image/png")}
    r_upload = await authed.post(
        f"/overnight-spots/{spot_recent_public_id}/media", files=files
    )
    assert r_upload.status_code == 200, r_upload.text
    recent_media_id = r_upload.json()["id"]

    # 4. Create a ShareLink with 72-hour delay that shares this spot
    share_res = await authed.post(
        "/share-links",
        json={
            "trip_id": trip_id,
            "name": "Recent Spot Share",
            "delay_hours": 72,
            "overnight_spot_ids": [str(spot_recent_public_id)],
        },
    )
    assert share_res.status_code == 201, share_res.text
    share_link = share_res.json()
    share_token = share_link["token"]

    # 5. Retrieve public share data and verify spot is hidden on list
    get_share_res = await client.get(f"/share/{share_token}")
    assert get_share_res.status_code == 200
    shared_spots = get_share_res.json()["overnight_spots"]
    assert len(shared_spots) == 0, "Spot should be filtered out from list"

    # 6. Attempt to download recent spot media direct via /share/{token}/media/{media_id}
    # MUST fail with 404 because last_stay_at is inside the privacy delay window
    media_res_recent = await client.get(f"/share/{share_token}/media/{recent_media_id}")
    assert media_res_recent.status_code == 404, (
        "Recent spot media should be inaccessible"
    )

    # 7. Add another spot outside the delay window (older)
    old_stay = datetime.now(timezone.utc) - timedelta(hours=96)
    async with SessionLocal() as s:
        from tracker_core.store.models import Trip as TripModel

        trip_db = (
            await s.execute(
                select(TripModel).where(TripModel.public_id == trip_public_id)
            )
        ).scalar_one()

        spot_old = OvernightSpot(
            user_id=account.user_id,
            trip_id=trip_db.id,
            name="Old Spot",
            lon=14.0,
            lat=53.0,
            nights_count=2,
            last_stay_at=old_stay,
        )
        s.add(spot_old)
        await s.commit()
        await s.refresh(spot_old)
        spot_old_public_id = spot_old.public_id

    # 8. Upload media for old spot
    files_old = {"file": ("old.png", png_content, "image/png")}
    r_upload_old = await authed.post(
        f"/overnight-spots/{spot_old_public_id}/media", files=files_old
    )
    assert r_upload_old.status_code == 200, r_upload_old.text
    old_media_id = r_upload_old.json()["id"]

    # 9. Create a ShareLink with 72-hour delay that shares this old spot
    share_res_old = await authed.post(
        "/share-links",
        json={
            "trip_id": trip_id,
            "name": "Old Spot Share",
            "delay_hours": 72,
            "overnight_spot_ids": [str(spot_old_public_id)],
        },
    )
    assert share_res_old.status_code == 201, share_res_old.text
    share_link_old = share_res_old.json()
    share_token_old = share_link_old["token"]

    # 10. Retrieve public share data and verify spot is visible on list
    get_share_res_old = await client.get(f"/share/{share_token_old}")
    assert get_share_res_old.status_code == 200
    shared_spots_old = get_share_res_old.json()["overnight_spots"]
    assert len(shared_spots_old) == 1, "Old spot should be in list"
    assert shared_spots_old[0]["name"] == "Old Spot"

    # 11. Attempt to download old spot media direct via /share/{token}/media/{media_id}
    # MUST succeed (200) because last_stay_at is outside the privacy delay window
    media_res_old = await client.get(f"/share/{share_token_old}/media/{old_media_id}")
    assert media_res_old.status_code == 200, media_res_old.text
    assert media_res_old.content == png_content


@pytest.mark.asyncio
async def test_public_share_downsampling(
    authed: httpx.AsyncClient,
    client: httpx.AsyncClient,
    account: Account,
):
    start = datetime.now(timezone.utc) - timedelta(days=5)
    trip_res = await authed.post(
        "/trips",
        json={
            "device_id": str(account.device_pid),
            "name": "Downsampling Test Trip",
            "started_at": start.isoformat(),
            "ended_at": None,
        },
    )
    assert trip_res.status_code == 200, trip_res.text
    trip = trip_res.json()
    trip_id = trip["id"]
    trip_public_id = trip["id"]

    async with SessionLocal() as s:
        from tracker_core.store.models import Position
        from tracker_core.store.models import Trip as TripModel

        trip_db = (
            await s.execute(
                select(TripModel).where(TripModel.public_id == trip_public_id)
            )
        ).scalar_one()

        positions = [
            Position(
                device_id=trip_db.device_id,
                time_id=start + timedelta(seconds=i * 10),
                lon=13.0,
                lat=52.0,
            )
            for i in range(24000)
        ]
        s.add_all(positions)
        await s.commit()

    share_res = await authed.post(
        "/share-links",
        json={
            "trip_id": trip_id,
            "name": "Big Trip Share",
            "delay_hours": 0,
            "overnight_spot_ids": [],
        },
    )
    assert share_res.status_code == 201, share_res.text
    share_link = share_res.json()
    share_token = share_link["token"]

    get_share_res = await client.get(f"/share/{share_token}")
    assert get_share_res.status_code == 200
    res_data = get_share_res.json()
    positions = res_data["positions"]

    assert len(positions) < 24000
    assert len(positions) == 12000


@pytest.mark.asyncio
async def test_share_link_unique_names(
    authed: httpx.AsyncClient,
    account: Account,
):
    """Verify that user cannot create or update a share link to a duplicate name."""
    # 1. Create a trip
    start = datetime.now(timezone.utc) - timedelta(days=5)
    trip_res = await authed.post(
        "/trips",
        json={
            "device_id": str(account.device_pid),
            "name": "Unique Name Test Trip",
            "started_at": start.isoformat(),
            "ended_at": None,
        },
    )
    assert trip_res.status_code == 200, trip_res.text
    trip_id = trip_res.json()["id"]

    # 2. Create first share link
    res1 = await authed.post(
        "/share-links",
        json={
            "trip_id": trip_id,
            "name": "My Beautiful Link",
            "delay_hours": 24,
        },
    )
    assert res1.status_code == 201, res1.text

    # 3. Try to create second share link with same name -> should fail with 400
    res2 = await authed.post(
        "/share-links",
        json={
            "trip_id": trip_id,
            "name": "My Beautiful Link",
            "delay_hours": 24,
        },
    )
    assert res2.status_code == 400, res2.text
    assert "already exists" in res2.json()["detail"]

    # 4. Create second share link with a different name -> should succeed
    res3 = await authed.post(
        "/share-links",
        json={
            "trip_id": trip_id,
            "name": "My Other Link",
            "delay_hours": 24,
        },
    )
    assert res3.status_code == 201, res3.text
    link3_id = res3.json()["id"]

    # 5. Try to update second share link to duplicate name -> should fail with 400
    res4 = await authed.patch(
        f"/share-links/{link3_id}",
        json={
            "name": "My Beautiful Link",
        },
    )
    assert res4.status_code == 400, res4.text
    assert "already exists" in res4.json()["detail"]

    # 6. Update second share link with its current name -> should succeed (noop)
    res5 = await authed.patch(
        f"/share-links/{link3_id}",
        json={
            "name": "My Other Link",
        },
    )
    assert res5.status_code == 200, res5.text

