# STACK.md — Technology Stack

## Languages & Runtimes
- **Python 3.11+** — API server, ingest server, shared core package
- **TypeScript / React 18** — Web frontend (SPA)
- **Node.js (build only)** — Vite bundler, no runtime Node in prod

## Backend Frameworks
| Layer | Library | Version |
|---|---|---|
| API framework | FastAPI | 0.136.1 |
| ASGI server | Uvicorn + uvloop | 0.46.0 |
| ORM | SQLAlchemy 2.0 async | 2.0.49 |
| Migrations | Alembic | 1.18.4 |
| Validation | Pydantic v2 | 2.13.3 |
| Auth | python-jose (HS256 JWT) + bcrypt | 3.5.0 / 5.0.0 |
| Rate limiting | slowapi | 0.1.9 |
| Logging | structlog | 25.5.0 |
| Config | pydantic-settings | 2.14.0 |

## Frontend Libraries
- **React 18** + Vite
- **MapLibre GL** — interactive map rendering
- **react-i18next** — i18n (English + at least 1 other locale)
- **TailwindCSS** (inferred from styles.css size, 54 KB)
- Cookie-based auth; no token in JS

## Databases
- **SQLite** (aiosqlite) — default dev + small self-hosted deployments
- **PostgreSQL 16** (asyncpg) — production/multi-tenant profile (`docker-compose` `postgres` profile)
- Two-database model: `identity.db` / `tracker_identity` (central) + per-tenant `tnt{id}.db` / `tracker_tenant_{id}` (data)

## Infrastructure / Deployment
- Docker Compose (4 services: `db`, `api`, `ingest`, `frontend`)
- **Traefik** reverse proxy + Let's Encrypt TLS
- Optional `mock` profile for simulated GPS feed
- Nginx serves the compiled SPA (`Dockerfile.web`)
- `DATA_DIR` volume mounts for SQLite files and uploaded media

## Dev Tooling
- **Ruff** (linter + formatter) — aggressive `ALL` rule set with explicit ignores
- **pytest + pytest-asyncio** — async test suite
- **httpx.ASGITransport** for integration tests (no real server needed)
- `yarn` (workspace root) — JS dependency management
