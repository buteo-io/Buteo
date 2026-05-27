# Buteo Technical Documentation

This folder contains detailed technical documentation for self-hosting and developing Buteo.

## Quick Links

- **[Self-Hosting Quickstart](self_hosting_quickstart.md)** — 15-minute VPS setup
- **[Production Deployment Guide](deployment.md)** — Traefik, security, and backups
- **[System Architecture](architecture.md)** — Architectural design and database ERD
- **[Environment Variable Reference](environment_variables.md)** — Configuration variables index

## Services and Ports

All published ports in `docker-compose.yml` are bound to `127.0.0.1` by default.

| Service | Host port -> container port | What it does |
|---|---|---|
| `frontend` | `${FRONTEND_PORT:-5124}` -> `80` | Web app (nginx serving built frontend) |
| `api` | `8765` -> `8765` | Main REST API, auth, trips, analytics, devices |
| `ingest` (Codec8) | `${INGEST_CODEC8_PORT:-5027}` -> same | Teltonika TCP ingest (FMC/FMB trackers, mock tracker) |
| `ingest` (OsmAnd) | `${INGEST_OSMAND_PORT:-8766}` -> same | OsmAnd/Traccar-style HTTP ingest endpoint |
| `db` | `55432` -> `5432` | PostgreSQL 16 |
| `mock-tracker` | none | Optional profile service that streams live fake GPS data |
| `tracking-admin` | none | Utility container for running CLI/admin tasks |

## Local Development Setup

### Prerequisites

- Docker + Docker Compose
- External Docker network named `traefik` (required by compose file)

```bash
docker network create traefik 2>/dev/null || true
```

### Configure Environment

```bash
cp .env.example .env
```

Set at least:

- `JWT_SECRET` (generate with `openssl rand -hex 32`)
- `POSTGRES_PASSWORD`

For local-only setup, you can keep defaults for `DOMAIN` and `API_DOMAIN` if Traefik routing is not used yet.

### Start Stack

```bash
docker compose up -d --build
```

Open app at `http://localhost:5124` (or `FRONTEND_PORT` override).

### Create First User and Device

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-user \
  --email you@example.com --password "your-secure-password"

docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei 123456789012345 --name "Camper"
```

### Stop Stack

```bash
docker compose down
```

## Production Setup (Containers + Traefik)

Use same `docker-compose.yml` with production env values.

### Requirements

- Traefik running on same Docker host
- External network `traefik` available
- TLS cert resolver configured in Traefik as `letsencrypt`

### Configure `.env`

Required production values:

- `JWT_SECRET` (32+ chars)
- `POSTGRES_PASSWORD`
- `DOMAIN` (public frontend hostname)
- optional `API_DOMAIN` (defaults to `api.${DOMAIN}`)
- `CORS_ORIGINS` including frontend origin(s)

Keep these secure defaults:

- `AUTH_COOKIE_SECURE=true`
- `DEV_INSECURE_COOKIES=false`

### Deploy

```bash
docker compose up -d --build
```

### First-time Bootstrap

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-user \
  --email you@example.com --password "your-secure-password"

docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei <your-imei> --name "Van Tracker"
```

## Linux/Windows Notes

Main gotcha: host networking alias behavior differs from macOS Docker Desktop.

- On macOS/Windows Docker Desktop, `host.docker.internal` usually works out of box.
- On Linux, `host.docker.internal` may not resolve unless mapped.
- If container must call service running on host (for example `API_UPSTREAM=host.docker.internal:8765`), add host-gateway mapping:

```yaml
# docker-compose override example
services:
  frontend:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- Alternative on Linux: use bridge gateway IP directly (often `172.17.0.1`).
- Ingest ports (`5027`, `8766`) are loopback-bound by default. Remote trackers/phones cannot reach them until you explicitly expose/forward/VPN.

## Seed Demo Data

Seed historical trip data for existing user/device:

```bash
docker compose run --rm api python -m tracker_core.cli.seed_demo \
  --email you@example.com --imei 123456789012345 --wipe
```

What this does:

- Generates realistic round trips (Dresden -> multiple destinations -> return)
- Inserts positions from 2024 until now
- `--wipe` clears existing positions for that device first
- `--no-osrm` disables road snapping (faster, less realistic)

Example without OSRM:

```bash
docker compose run --rm api python -m tracker_core.cli.seed_demo \
  --email you@example.com --imei 123456789012345 --wipe --no-osrm
```

## Live Dummy Data

### Option 1: Compose Profile (Recommended)

```bash
docker compose --profile mock up -d mock-tracker
```

This starts continuous fake tracker stream into `ingest` using `MOCK_IMEI` (default `123456789012345`).

### Option 2: Run Script Directly

```bash
python scripts/mock_tracker.py --host 127.0.0.1 --port 5027 \
  --imei 123456789012345 --interval 2
```

## CLI Reference

Run commands either:

- In container: `docker compose run --rm api python -m ...`
- Or in backend venv: `python -m ...`

### `tracker_core.cli.manage` Commands

| Command | Purpose | Example |
|---|---|---|
| `init-db` | Run Alembic migrations to latest | `python -m tracker_core.cli.manage init-db` |
| `create-user --email --password` | Create user (password min 12 chars) | `python -m tracker_core.cli.manage create-user --email you@example.com --password "your-secure-password"` |
| `reset-password --email --password` | Reset password, invalidate sessions | `python -m tracker_core.cli.manage reset-password --email you@example.com --password "your-secure-password"` |
| `create-device --email --imei --name` | Register tracker device for user | `python -m tracker_core.cli.manage create-device --email you@example.com --imei 123456789012345 --name "Camper"` |
| `revoke-device --imei` | Revoke device; ingest rejects new fixes | `python -m tracker_core.cli.manage revoke-device --imei 123456789012345` |
| `deactivate-user --email` | Disable login for user | `python -m tracker_core.cli.manage deactivate-user --email you@example.com` |
| `activate-user --email` | Re-enable login | `python -m tracker_core.cli.manage activate-user --email you@example.com` |
| `list-users` | List users | `python -m tracker_core.cli.manage list-users` |
| `list-devices` | List devices | `python -m tracker_core.cli.manage list-devices` |

### `tracker_core.cli.seed_demo` Command

| Command | Purpose | Example |
|---|---|---|
| `--email --imei [--wipe] [--seed] [--no-osrm]` | Seed realistic historical trip points for one device | `python -m tracker_core.cli.seed_demo --email you@example.com --imei 123456789012345 --wipe` |

## REST API Docs

REST endpoints are documented in Swagger/OpenAPI from API service.

- Local (if docs enabled): `http://localhost:8765/docs`
- OpenAPI JSON: `http://localhost:8765/openapi.json`

In production, docs are disabled by default via `DOCS_ENABLED=false`.

## Supported GPS Devices

Buteo supports three categories of GPS tracking devices. Choose the one that matches your hardware.

| Device Category | Protocol | Port | Use Case |
|---|---|---|---|
| Teltonika hardware trackers (FMC/FMB series) | Codec 8 TCP | `5027` | Dedicated GPS devices, vehicles |
| Traccar Client (mobile app) | OsmAnd HTTP | `8766` | Android/iOS phone as tracker |
| OwnTracks (mobile app) | OwnTracks HTTP | `8766` | Privacy-focused location sharing |

---

### Teltonika Hardware Trackers (FMC/FMB Series)

Tested with: **Teltonika FMC920**

These are dedicated GPS devices that send data over TCP. They support various protocols; Buteo implements **Codec 8** and **Codec 8E**.

#### 1. Register the device

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei <your-tracker's-imei> --name "Van Tracker"
```

Find the IMEI on the device label or via SMS command `getimei`.

#### 2. Configure the tracker

Send SMS commands to the device (or configure via Teltonika Configurator, only for Windows):

```
setparam 2001:your-apn;2002:your-apn-user;2003:your-apn-pass;2004:your-domain.com;2005:5027;2006:0
```

Replace:
- `your-apn` — your mobile carrier's APN
- `your-apn-user` — APN username (omit `2002:` part if not required)
- `your-apn-pass` — APN password (omit `2003:` part if not required)
- `your-domain.com` — your server's public hostname or IP
- `5027` — your `INGEST_CODEC8_PORT` (default)

Parameter IDs:
- `2001` – APN
- `2002` – APN username (optional)
- `2003` – APN password (optional)
- `2004` – Domain
- `2005` – Port
- `2006` – Protocol (`0` = TCP, `1` = UDP)

#### 3. Enable data sending

Use the Teltonika Configurator software to set "Data Sending Interval" to your desired frequency (e.g., 30 seconds). This is configured in the **Data Acquisition** settings.

#### Optional: Codec 8E

If your device uses Codec 8E (extended), Buteo handles it automatically. The same port and configuration applies.

---

### Traccar Client (Mobile App)

Works with: **Traccar Client for Android**, **Traccar Client for iOS**, **GPSLogger** (with OsmAnd protocol)

This turns a smartphone into a GPS tracker using the OsmAnd/Traccar protocol.

#### 1. Register the device

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei <desired-identifier> --name "My Phone"
```

The IMEI/identifier must match what you configure in the app.

#### 2. Configure Traccar Client

In the Traccar Client app:

- **Server URL**: `https://your-domain.com:8766/traccar_client`
- **Identifier**: `<your-registered-imei>`
- **Device Name**: anything

For **GPSLogger** (Android):
- Select "OsmAnd" protocol
- Server: `https://your-domain.com:8766/traccar_client`
- Device ID: `<your-registered-imei>`

#### 3. Adjust tracking frequency

In the app settings, set the interval (e.g., 30 seconds or 1 minute). Higher frequency = more battery drain.

---

### OwnTracks (Mobile App)

Works with: **OwnTracks for Android**, **OwnTracks for iOS**

OwnTracks is a privacy-focused alternative that can work in HTTP mode.

#### 1. Register the device

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei <device-name> --name "My Phone"
```

The identifier can be any string (not just numeric IMEI).

#### 2. Configure OwnTracks

In OwnTracks settings:

- **Mode**: HTTP
- **URL**: `https://your-domain.com:8766/owntracks`
- **Authentication**: Off (device auth is via identifier)
- **Device ID**: `<your-registered-identifier>`
- **User ID**: any (e.g., your email)


#### 3. Set location publish interval

OwnTracks → Settings → Location → Publish interval (e.g., "Significant" or "Move").

---

## GPS Tracker Ingest (Technical)

### Traccar Client (iOS/Android, GPSLogger)

Traccar/OsmAnd protocol endpoint runs on ingest service (`INGEST_OSMAND_PORT`, default `8766`):

```text
GET/POST http(s)://<host>:8766/traccar_client?id=<imei>&lat=<>&lon=<>&timestamp=<unix_or_iso>&speed=<knots>&bearing=<deg>&altitude=<m>
```

Notes:

- `id` must match registered device IMEI.
- `speed` expected in knots and stored as km/h.
- `timestamp` accepts unix seconds, unix millis, or ISO-8601.
- Responses: `200` success, `400` bad payload, `401` unknown device, `410` revoked device.

Security model:

- No per-request token; IMEI acts as credential.
- Protect endpoint with TLS + IP allow-list and/or VPN/WireGuard.

iOS Traccar Client quick config:

- Server URL: `https://<your-host>:8766/traccar_client`
- Identifier: registered IMEI

### OwnTracks HTTP

OwnTracks HTTP endpoint runs on ingest service (`INGEST_OSMAND_PORT`, default `8766`):

```text
POST http(s)://<host>:8766/owntracks
```

Expected payload shape follows OwnTracks JSON docs:

- `_type=location` messages persist positions (`lat`, `lon`, `tst`, optional `vel`, `alt`).
- non-location payloads (e.g. `_type=transition`) are accepted and ignored.
- empty payloads are accepted and ignored.

Device identifier resolution order:

- `id` query param
- `X-Limit-D` header (recommended in OwnTracks HTTP mode)
- `d` query param
- payload `id` / `deviceid` / `device_id`
- device segment from payload `topic` (e.g. `owntracks/user/device`)
- payload `tid`

Resolved value must match registered device IMEI.

### Teltonika Codec 8 (Hardware Trackers)

To connect hardware tracker:

1. Register tracker IMEI in app:

```bash
python -m tracker_core.cli.manage create-device --email you@example.com --imei <imei> --name "Van"
```

2. Configure device GPRS server to `<your-host>:5027` (or your `INGEST_CODEC8_PORT`).
3. Tracker sends IMEI handshake, server replies accept/reject, then streams Codec 8/8E AVL records.

Protocol implementation lives in `apps/ingest/ingest/codec8/codec8.py`.

Reference: [Teltonika Codec protocol docs](https://wiki.teltonika-gps.com/view/Codec).

## Security Notes

- Keep `JWT_SECRET` random and private.
- Keep ingest ports private unless protected (VPN/reverse proxy/TLS tunnel).
- In production, keep secure cookie settings enabled.
