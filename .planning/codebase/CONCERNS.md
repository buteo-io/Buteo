# CONCERNS.md — Technical Concerns & Risks

## Architecture Concerns

### 1. `App.tsx` God Component (~977 lines)
- Owns all server state (trips, places, shares, spots, positions) + all UI modal state
- No React Query / SWR — manual `useState` + `useEffect` fetching throughout
- High re-render risk; difficult to split without prop drilling or more contexts
- **Risk**: Medium-high — will slow feature additions as app grows

### 2. Tenant DB Migration Race on First Request
- `TenantDatabaseManager.ensure_migrated` runs Alembic synchronously (via `asyncio.to_thread`) on the first request per tenant per runtime
- Protected by `asyncio.Lock` per tenant — correct, but cold-start latency spike on first request
- If the API restarts while a request is in-flight, migration state in `migrated_urls` is lost (idempotent so re-run is safe)
- **Risk**: Low (idempotent), but worth noting

### 3. No Refresh Token / Token Rotation
- JWTs expire per `JWT_EXPIRE_MIN` (default 24h); sliding window via cookie re-set on every 2xx
- If `JWT_EXPIRE_MIN` is long and user is inactive, token stays valid until `token_version` is bumped
- No refresh token flow — logout is the only revocation mechanism besides version bump
- **Risk**: Low for self-hosted; relevant if multi-user SaaS

### 4. File Storage — Local Filesystem Only
- Media stored at `DATA_DIR/uploads/{user_id}/{public_id}/`
- No S3 / object store abstraction; migration to cloud storage requires code changes
- Trip deletion manually walks spots and calls `shutil.rmtree` — race if upload in progress
- **Risk**: Medium for scale; acceptable for self-hosted

### 5. OsmAnd Ingest Auth — IMEI Only
- The `/traccar_client` endpoint authenticates solely via `id` param (IMEI)
- IMEI visible in URL query string (GET requests) — logs, proxies may capture it
- Rate limiting (150/min) and IP allow-listing at proxy are the defense layers
- **Risk**: Medium — acceptable self-hosted pattern, needs proxy hardening in prod

## Code Quality Concerns

### 6. Public Share Token Lookup — Full Table Scan Risk
- `ShareLink.token` is indexed (`unique=True`), so lookups are O(log n) — fine
- Token stored as SHA-256 digest; pepper falls back to `JWT_SECRET` if `SHARE_TOKEN_PEPPER` unset — coupling of concerns
- **Risk**: Low

### 7. `CoreSessionLocal` Used Directly in Tests
- Some tests (`test_trips_api.py`) call `CoreSessionLocal` directly to seed positions
- This bypasses `TenantDatabaseManager` routing — works because test fixtures explicitly set `current_tenant_id` context var
- Can silently break if tenant routing changes
- **Risk**: Low-medium

### 8. Analytics `detect_overnights` Called Twice for Trip Stats
- `GET /trips/{id}/stats` calls `analytics.detect_overnights(pts)` inline (returns raw count)
- Separate `POST /trips/{id}/overnight-spots/detect` runs `detect_and_persist_overnights` (full service)
- Stats endpoint count and persisted count may diverge if not run together
- **Risk**: Low (cosmetic), but confusing UX

### 9. No Frontend Error Boundary
- No React `ErrorBoundary` component found
- Unhandled errors in map/panel components will crash the entire SPA
- **Risk**: Low-medium for UX reliability

### 10. `seed_demo.py` OSRM External Dependency
- CLI demo seeder calls OSRM public API (`router.project-osrm.org`) — network dependency
- Will fail in airgapped environments or if OSRM is down
- **Risk**: Low (dev/demo only)

## Security Observations (Non-blocking)
- `IMEI` field on `Device` model must never appear in public/share API responses — verified in `public_share.py`
- `DOCS_ENABLED=false` in production Docker (no `/docs` exposure) — good
- `data_dir` validated at startup for SQLite; `DATA_DIR` env var required in Docker
- JWT secret validated at startup (refuses known defaults, enforces 32+ chars) — good practice
