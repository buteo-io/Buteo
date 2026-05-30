"""Liveness probe."""
from __future__ import annotations

import httpx


async def test_healthz_ok(client: httpx.AsyncClient):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True
