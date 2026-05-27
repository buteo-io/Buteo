# CONVENTIONS.md — Code Conventions

## Python Style
- **Ruff** with `select = ["ALL"]` and explicit per-rule ignores (see `pyproject.toml`)
- Target: Python 3.12, line length 120
- Docstring style: Google (`convention = "google"`)
- `from __future__ import annotations` in all Python files
- Relative imports inside `api/` subpackage (explicitly allowed, `TID252` ignored)

## ID / Public API Conventions
- All public-facing IDs are **prefixed UUIDs**: `usr_`, `ent_`, `dev_`, `trp_`, `plc_`, `ovs_`, `shl_`, `med_`
- Internal integer PKs never appear on the wire
- `PrefixUUID` custom Pydantic type enforces format in request/response schemas

## Database Conventions
- Every mutable row has `created_at` + `updated_at` (UTC, `DateTime(timezone=True)`)
- Emails stored lowercase; `CHECK` constraint enforces it
- Ownership NOT duplicated: `Trip.user_id` does not exist — owner derived via `device.user_id`
- `Device.revoked_at` is soft-delete; ingest rejects revoked devices
- `Trip.ended_at = NULL` means ongoing trip; partial unique index enforces one-per-device
- `CHECK` constraints on lat/lon ranges on `Position`, `Place`, `OvernightSpot`

## API / FastAPI Conventions
- `response_model=` kept on all endpoints (documents intent, robust to refactor)
- `model_fields_set` used for PATCH endpoints to distinguish missing-key vs explicit-null
- `IntegrityError` on ongoing-trip unique violation → HTTP 409 (not 500)
- Logging uses `logger.info(event, extra={...})` structured pattern throughout
- `/healthz` always available, never leaks DB error strings to client

## Auth / Security Conventions
- `dummy_verify_password()` called on unknown-email login branch (timing-safe)
- `JWT_SECRET` validated at startup: refuses known-default values, enforces 32+ chars
- Cookie: `httpOnly=True`, `secure=True`, `samesite="strict"` in production
- Share token stored as `SHA-256(pepper:token)` — plaintext never persisted

## Frontend Conventions
- `credentials: 'include'` on all fetch calls (cookie auth, no JS token access)
- API errors normalized: Pydantic 422 arrays and HTTPException strings both → single human string
- `UTCModel` base class ensures datetime serialization consistency
- Context providers: `DateRangeContext`, `EntityContext`, `MapStateContext` wrap `App`
- Plugin pattern: `initDummyPlugin()` called at module load in `main.tsx`

## Testing Conventions
- All tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- `conftest.py` provisions full tenant stack per test: identity DB + tenant DB + user + device
- `httpx.ASGITransport` for API integration tests (no network)
- Rate limiters disabled in test setup (`limiter.enabled = False`)
- Cross-tenant isolation tested with `other_authed` fixture
- `_purge()` tears down the tenant + SQLite file after each test
