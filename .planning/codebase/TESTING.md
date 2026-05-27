# TESTING.md — Testing Strategy

## Test Infrastructure
- **Framework**: pytest + pytest-asyncio (`asyncio_mode = "auto"`, session-scoped loop)
- **HTTP client**: httpx `ASGITransport` — no real server, direct ASGI dispatch
- **Location**: `apps/api/api/tests/` (~19 test files)
- **Fixtures**: `conftest.py` provides `account`, `other_account`, `client`, `authed`, `other_authed`, `osmand_client`

## Fixture Setup Pattern
Each test gets a fully isolated tenant:
1. Register `Tenant` in identity DB
2. Run `init_core_db` on fresh SQLite file
3. Create `User` + `Entity` + `Device` in tenant DB
4. Register `GPSDevice` in identity DB
5. Teardown: `_purge()` clears identity rows + deletes SQLite file

## Test Coverage (known files)
| File | Focus |
|---|---|
| `test_auth_api.py` | Login, logout, token revocation, rate limiting |
| `test_auth.py` | JWT make/parse unit tests |
| `test_trips_api.py` | Trip CRUD, ongoing lifecycle, stats, cascade deletes, overnight spots |
| `test_places_api.py` | Place CRUD, trip linking, media |
| `test_analytics_api.py` | Trips, overnights, mileage, summary endpoints |
| `test_analytics.py` | Pure analytics unit tests (haversine, stop detection) |
| `test_osmand.py` | OsmAnd ingest acceptance (15 KB) |
| `test_codec8.py` | Codec 8 binary protocol parsing |
| `test_public_share_media.py` | Share link media serving + privacy filters (13 KB) |
| `test_dynamic_routing.py` | Tenant DB routing isolation |
| `test_identity_db.py` | Identity DB CRUD + cascade |
| `test_cli.py` | CLI commands (create-user, seed-demo, etc.) |
| `test_devices_api.py` | Device listing/revocation |
| `test_entities_api.py` | Entity CRUD |
| `test_positions_api.py` | Raw position endpoints |
| `test_schemas.py` | PrefixUUID validation |
| `test_healthz.py` | /healthz probe |

## Known Gaps / Observations
- No dedicated frontend tests (no Playwright, Vitest, or Jest setup found)
- `conftest.py` imports from both `api` and `ingest` packages — requires both in path
- `CoreSessionLocal` used directly in some tests to seed positions (bypasses tenant routing — OK for test fixtures)
- Rate limiter disabled globally in test suite (`_auth_module.limiter.enabled = False`)

## Running Tests
```bash
cd apps/api
python -m pytest api/tests/ -v
```
