# Buteo Environment Variable Reference

All operational aspects of the Buteo application—security parameters, database settings, port binds, file attachment sizing limits, and CORS policies—are configured using environment variables. 

On startup, Pydantic-Settings parses variables from the host environment, fallback `.env` files, or Docker Compose overrides.

---

## 1. Secrets & Core Security

| Variable | Type | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | `string` | *(None)* | **REQUIRED.** High-entropy secret key used to sign and verify session JWTs. Must be at least 32 characters. Generate with `openssl rand -hex 32`. Startup fails if unset or matches known weak defaults. |
| `SHARE_TOKEN_PEPPER` | `string` | `""` (defaults to `JWT_SECRET`) | Dedicated salt/pepper string used to hash public share-link tokens in the database. Changing this invalidates all current public share links. |
| `AUTH_COOKIE_NAME` | `string` | `"tracker_session"` | Key name of the HTTP-only cookie containing the user's JSON Web Token. |
| `AUTH_COOKIE_SECURE` | `boolean` | `true` | When `true`, session cookies are restricted to HTTPS connections. Keep `true` in all production systems. |
| `DEV_INSECURE_COOKIES` | `boolean` | `false` | Set to `true` **only** for plain-HTTP local development. Overrides `AUTH_COOKIE_SECURE` to allow session preservation over standard HTTP. |

---

## 2. Server & Routing Context

| Variable | Type | Default | Description |
|---|---|---|---|
| `DOMAIN` | `string` | `"sub.yourdomain.com"` | Public domain serving the frontend UI. Used in Traefik router rules and CORS matching. |
| `API_DOMAIN` | `string` | `"api.sub.yourdomain.com"` | Public subdomain routed to the REST API. Defaults to `api.${DOMAIN}` in compose if unset. |
| `CORS_ORIGINS` | `string` | `"http://localhost:5173"` | Comma-separated list of origins permitted to issue CORS requests. Set to `https://${DOMAIN}` in production. |
| `DOCS_ENABLED` | `boolean` | `true` | Enables or disables OpenAPI/Swagger documentation at `/docs` and `/redoc` endpoints. Set to `false` in production. |
| `LOG_LEVEL` | `string` | `"INFO"` | Logging verbosity. Supported options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |

---

## 3. Database Persistence

Buteo utilizes a highly secure multi-tenant database configuration with one database per tenant/user. It automatically configures the correct database engine based on `DATABASE_TYPE`.

- **Option A (SQLite - Default)**: Active when `DATABASE_TYPE` is `"sqlite"`. Creates a central `identity.db` in `DATA_DIR` and individual isolated `tenant_{tenant_id}.db` databases.
- **Option B (PostgreSQL)**: Active when `DATABASE_TYPE` is `"postgres"`. Creates a central `tracker_identity` catalog database and individual isolated `tracker_tenant_{tenant_id}` databases on the target host.

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_TYPE` | `string` | `"sqlite"` | **REQUIRED.** Choose `"sqlite"` or `"postgres"` engine for multi-tenant isolation. |
| `DATA_DIR` | `string` | `None` | Host or container mount directory for SQLite databases. Required when `DATABASE_TYPE=sqlite`. Central database will be at `{DATA_DIR}/identity.db`. |
| `POSTGRES_USER` | `string` | `"tracker"` | Username credential for Postgres. Required when `DATABASE_TYPE=postgres`. |
| `POSTGRES_PASSWORD` | `string` | `"change-me"` | Password credential for Postgres. Required when `DATABASE_TYPE=postgres`. |
| `POSTGRES_DB` | `string` | `"tracker"` | Primary/default catalog database name in Postgres. |
| `DB_HOST` | `string` | `"localhost"` | Postgres server host address. Required when `DATABASE_TYPE=postgres`. |
| `DB_PORT` | `string` | `"55432"` | Postgres connection port. Required when `DATABASE_TYPE=postgres`. |

---

## 4. Port and Bind Bindings

| Variable | Type | Default | Description |
|---|---|---|---|
| `API_HOST` | `string` | `"0.0.0.0"` | Bind address for the main FastAPI REST application. |
| `API_PORT` | `int` | `8765` | Exposed port for the REST API application. |
| `API_UPSTREAM` | `string` | `"api:8765"` | Nginx proxy target configured in the frontend web container to forward `/api/` traffic. |
| `INGEST_HOST` | `string` | `"0.0.0.0"` | Bind address for the TCP and HTTP ingest processes. |
| `INGEST_CODEC8_PORT` | `int` | `5027` | Teltonika TCP binary protocol receiver port. |
| `INGEST_OSMAND_PORT` | `int` | `8766` | OsmAnd, Traccar client, and OwnTracks HTTP endpoint port. |
| `FRONTEND_PORT` | `int` | `8080` (or `5124` in compose) | Exposed host port serving static HTML/JS/CSS assets via Nginx. |
| `VITE_API_TARGET` | `string` | `"http://127.0.0.1:8765"` | Local API endpoint proxy target used during local Node development (`npm run dev`). |

---

## 5. Attachment & Upload Constraints

| Variable | Type | Default | Description |
|---|---|---|---|
| `MAX_IMAGE_SIZE_MB` | `int` | `20` | Maximum allowed size in Megabytes for place/overnight spot picture uploads. |
| `MAX_VIDEO_SIZE_MB` | `int` | `500` | Maximum allowed size in Megabytes for video attachments. |
| `MAX_AUDIO_SIZE_MB` | `int` | `50` | Maximum allowed size in Megabytes for voice clips/audio notes. |
