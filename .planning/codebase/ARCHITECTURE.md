# ARCHITECTURE.md — System Architecture

## Overview
Buteo (internal name: TrackMy) is a self-hostable GPS tracking platform.  
Three deployable services share one Python package (`tracker_core`).

```
GPS Devices  ──TCP:5027──▶  ingest  ──────────────────▶  tenant DB
Mobile apps  ──HTTP:8766──▶  ingest                        ▲
Browser      ──HTTPS──────▶  frontend (Nginx)              │
                          ▶  api ──── identity DB ──────────┘
```

## Services

### `apps/api` — REST API (FastAPI)
- Authenticated by JWT cookie or `Authorization: Bearer`
- 12 routers: `auth`, `devices`, `entities`, `positions`, `places`, `analytics`, `trips`, `overnight_spots`, `share_links`, `public_share`, `media`, `entities`
- Alembic auto-runs tenant migrations on first session per runtime
- `GET /healthz` — DB liveness probe

### `apps/ingest` — Location Ingest (FastAPI + asyncio TCP)
- Codec 8 TCP handler + OsmAnd/OwnTracks HTTP handler
- Looks up IMEI → tenant in identity DB, then writes `Position` rows to tenant DB
- Does NOT handle auth migrations (API is responsible)

### `apps/web` — React SPA
- Single `App.tsx` orchestrates all state; context providers for DateRange, Entity, MapState
- `api.ts` — typed fetch wrapper, cookie auth, FastAPI error normalizer
- MapLibre GL for map rendering
- Plugin registry for optional frontend features
- PWA service worker registered in production

### `packages/core/tracker_core` — Shared Domain Package
- **`store/models.py`** — all ORM models
- **`store/identity_db.py`** — central identity DB engine (tenants, GPS device routing)
- **`store/core_db.py`** — per-tenant DB base + migrations
- **`store/tenant_db_manager.py`** — `TenantDatabaseManager` singleton; caches engines per tenant; runs migrations once per runtime via `asyncio.Lock`
- **`analytics.py`** — pure functions: haversine, stop detection, overnight detection, GPX/CSV export
- **`overnight_service.py`** — incremental overnight spot detection + persistence
- **`queries.py`** — `positions_in_window_capped` (200k point cap)
- **`cli/manage.py`** — admin CLI (create-user, create-entity, create-device, seed-demo)
- **`internal/appctx/config.py`** — `AppConfig` (pydantic-settings, reads `.env`)

## Multi-Tenancy Model
- **Identity DB** (single, shared): `tenants` + `gps_devices` tables
- **Tenant DB** (one per user): isolated SQLite file or PostgreSQL schema
- `TenantDatabaseManager` resolves `tenant_id` from JWT claim → routes session to correct DB engine
- `contextvars.ContextVar[str]` carries `current_tenant_id` within each async request context

## Auth Flow
1. `POST /auth/login` → verify in identity DB → issue HS256 JWT → set `httpOnly` cookie
2. `current_user` FastAPI dep → extract JWT → validate `Tenant.token_version` → route to tenant DB → validate `User`
3. Public share: token hash lookup in identity DB → routes to correct tenant DB without user credentials

## Data Model Highlights
- `User → Entity → Device → Position` (ownership chain)
- `Trip` time-windows device positions; owner derived via `device.user_id` (no duplicate FK)
- `Place ↔ Trip` many-to-many via `place_trips` junction
- `OvernightSpot` belongs to `Trip`; auto-detected by `overnight_service`
- `ShareLink` has privacy filters (delay, blur, time range, place/spot subset); token is SHA-256 hashed
- All public-facing IDs are prefixed UUIDs (`usr_`, `dev_`, `trp_`, `plc_`, `ovs_`, `shl_`); internal int PKs never exposed
