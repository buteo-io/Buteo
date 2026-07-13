"""Devices listing endpoint."""

from __future__ import annotations

import httpx

from .conftest import Account


async def test_list_devices_requires_auth(client: httpx.AsyncClient):
    assert (await client.get("/devices")).status_code == 401


async def test_list_devices_returns_owned(authed: httpx.AsyncClient, account: Account):
    r = await authed.get("/devices")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    d = body[0]
    assert d["imei"] == account.device_imei
    assert d["id"] == str(account.device_pid)


async def test_list_devices_isolated_per_user(
    other_authed: httpx.AsyncClient,
    account: Account,
):
    # Bob must not see Alice's device.
    r = await other_authed.get("/devices")
    assert r.status_code == 200
    body = r.json()
    assert all(d["id"] != str(account.device_pid) for d in body)
