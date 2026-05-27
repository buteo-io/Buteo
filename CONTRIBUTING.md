# Local Development & Debugging

This guide helps you set up a local development environment for Buteo to debug, customize, or inspect the codebase.

---

## 🛠️ Local Development Setup

Buteo uses a monorepo structure:
- `apps/api`: Python FastAPI backend.
- `apps/ingest`: Telemetry ingestion servers (Codec 8 / OsmAnd / OwnTracks).
- `apps/web`: React / TypeScript frontend.
- `packages/core`: Shared database models, migrations, and core business logic.

### Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- Python 3.11+ (for local CLI / tests)
- Node.js 18+ & Yarn (for local frontend dev)

### Docker Dev Workflow (Recommended)

1. **Clone repository and set up environment:**
   ```bash
   git clone https://github.com/buteo-io/Buteo.git
   cd buteo
   cp .env.example .env
   ```

2. **Generate secure JWT secret:**
   Edit `.env` and replace `JWT_SECRET` with the output of:
   ```bash
   openssl rand -hex 32
   ```

3. **Start services:**
   ```bash
   docker compose up -d --build
   ```

4. **Initialize development user & tracker:**
   ```bash
   docker compose run --rm api python -m tracker_core.cli.manage create-user --email dev@example.com --password "dev-password"
   docker compose run --rm api python -m tracker_core.cli.manage create-device --email dev@example.com --imei 123456789012345 --name "Dev Tracker"
   ```

---

## 🐍 Backend Guidelines (Python)

### Environment & Package Management
Backend utilizes `packages/core`, `apps/api`, and `apps/ingest`.
- Local development paths are mapped using python paths. To run CLI tools locally without Docker, prefix with `PYTHONPATH=apps/api:packages/core:apps/ingest`.

### Formatting & Linting
We use **Ruff** for code style, formatting, and linting:
```bash
ruff check apps/api apps/ingest packages/core
ruff format apps/api apps/ingest packages/core
```

### Running Tests
Tests use `pytest`:
```bash
# Run all tests
PYTHONPATH=apps/api:packages/core:apps/ingest pytest

# Or inside Docker
docker compose run --rm api pytest
```

---

## ⚛️ Frontend Guidelines (React & TypeScript)

The web app lives inside `apps/web`.

### Setup & Run
1. Install dependencies:
   ```bash
   cd apps/web
   yarn install
   ```

2. Start the development server (runs with hot reload):
   ```bash
   yarn dev
   ```

### Code Style
- Keep components small and focused.
- Use **TailwindCSS** for styles. Add custom global CSS only in `apps/web/src/styles.css`.
- Verify TypeScript types compile:
   ```bash
   yarn tsc --noEmit
   ```

