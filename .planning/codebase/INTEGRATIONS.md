# INTEGRATIONS.md — External Integrations

## GPS Device Protocols

### Teltonika / Codec 8 (TCP)
- Port: 5027 (configurable via `INGEST_CODEC8_PORT`)
- Binary AVL packet stream over persistent TCP
- IMEI is the device credential (no per-packet token)
- `apps/ingest/ingest/codec8/` — parser

### OsmAnd / Traccar Client (HTTP)
- Port: 8766 (`INGEST_OSMAND_PORT`)
- `GET/POST /traccar_client` — query params: `id`, `lat`, `lon`, `timestamp`, `speed`, `altitude`
- `POST /owntracks` — OwnTracks HTTP-mode JSON (non-location payloads silently ignored)
- Per-IP rate limit: 150/min, 10 000/hr

## Authentication
- **JWT HS256** — issued on login, stored in `httpOnly; Secure; SameSite=Strict` cookie
- Cookie auto-slid on each 2xx response (keep-alive for active PWA sessions)
- `token_version` counter on `Tenant` row invalidates all outstanding tokens on logout/reset
- Share links use a separate SHA-256(pepper+token) digest — never exposes internal IDs

## Public Share Links
- `/share/:token` — unauthenticated route handled by `public_share.py`
- Privacy controls: `delay_hours` (default 72h), `blur_meters` (default 100m), optional place/overnight-spot subset, time-range override, `is_active` toggle

## File Storage
- Local filesystem under `DATA_DIR/uploads/{user_id}/{spot_or_place_public_id}/`
- No S3 / object storage integration currently
- Supported: image (≤20 MB), video (≤500 MB), audio (≤50 MB)
- Media served via `GET /media/{media_id}/serve`

## Reverse Proxy (Traefik)
- Automatic TLS via Let's Encrypt (`letsencrypt` cert resolver)
- Security headers middleware: HSTS, CSP, X-Frame-Options, etc.
- Routes: `/` → frontend, `/api/*` + `/share/*` → API, `/traccar_client` + `/owntracks` → ingest

## Plugin System
- `api/plugins/loader.py` — dynamic import of Python packages/modules in `api/plugins/`
- Each plugin exposes either `register_plugin(app)` or a `router` variable
- Dummy plugin included as reference (`api/plugins/dummy/`)
- Frontend plugin registry at `src/plugins/registry.ts`

## OSRM (Route Planning — CLI only)
- `seed_demo.py` calls OSRM public API to generate realistic polylines for demo data seeding
- Not used in production API
