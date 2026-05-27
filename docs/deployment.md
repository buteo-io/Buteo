# TrackMy Production Deployment Guide

This guide describes how to run and secure TrackMy in a production environment. 

---

## 1. Prerequisites

Before deploying TrackMy to a production server, ensure you have the following ready:

- **A Virtual Private Server (VPS)** or dedicated physical server with Linux (Ubuntu 22.04+ recommended).
- **Docker & Docker Compose** installed.
- **A Fully Qualified Domain Name (FQDN)** with DNS records (`A` / `AAAA`) configured to point to your server IP:
  - `track.yourdomain.com` (Frontend UI)
  - `api.track.yourdomain.com` (REST API & Auth endpoints)
- **Traefik Reverse Proxy** running on the host as your edge router (or another reverse proxy like Nginx/Caddy configured to route TLS traffic).

### Network Configuration
TrackMy's production `docker-compose.yml` relies on an external Docker network named `traefik`. Create it prior to launching the stack:
```bash
docker network create traefik
```

---

## 2. Recommended Production Layout

A typical production directory layout on the server filesystem:

```text
/opt/trackmy/
├── .env                  # Secrets and configuration parameters
├── docker-compose.yml    # Standard stack orchestrator
└── data/                 # Mounted volume directory (automatically created)
    ├── identity.db       # Central identity registry SQLite database
    ├── tenant_foo.db     # Isolated database for tenant "foo"
    ├── tenant_bar.db     # Isolated database for tenant "bar"
    ├── backups/          # Database backup target directory
    └── media/            # Uploaded trip and place images/attachments
```

---

## 3. Configuration Step-by-Step

### Step 1: Clone and Copy Configuration
Copy the production environment template:
```bash
cp .env.example .env
```

### Step 2: Configure Environment Variables
Edit `.env` using a terminal text editor (such as `nano` or `vim`). Adjust the following crucial production values:

```ini
# Generate a strong 32-character hex secret: openssl rand -hex 32
JWT_SECRET=8167fcf99a8c...d05e

# Public domain names
DOMAIN=track.yourdomain.com
API_DOMAIN=api.track.yourdomain.com

# Database Connection (e.g. SQLite local file)
DATABASE_URL=sqlite+aiosqlite:////data/core.db

# Production Cookie Security (CRITICAL for HTTPS)
AUTH_COOKIE_SECURE=true
DEV_INSECURE_COOKIES=false

# CORS Origins (Match your public frontend URL)
CORS_ORIGINS=https://track.yourdomain.com

# Ingest and UI ports
FRONTEND_PORT=5124
INGEST_CODEC8_PORT=5027
INGEST_OSMAND_PORT=8766
```
*(For complete configuration options, consult `@/Users/noahm/private/trackmy-core/docs/environment_variables.md`.)*

---

## 4. Run the Stack

Launch the unified Docker stack in detached mode:
```bash
docker compose up -d --build
```

Verify that all services started successfully:
```bash
docker compose ps
```

---

## 5. Bootstrap Administrative Access

Since TrackMy does not open a public registration endpoint for security, your first admin user and tracking device must be provisioned via the command-line interface.

### Step 1: Create Admin User Account
```bash
docker compose run --rm api python -m tracker_core.cli.manage create-user \
  --email you@example.com --password "your-secure-password"
```
*(Passwords must be at least 12 characters long.)*

### Step 2: Create Tracked Device
```bash
docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei 123456789012345 --name "Campervan"
```
*Note: The `--imei` parameter must match the unique hardware identifier sent by your GPS tracking client.*

---

## 6. Security Hardening

To preserve location privacy and prevent unauthorized access, enforce the following hardening measures:

### A. Ingest Server Isolation
The HTTP and TCP ingest ports (`8766` and `5027` respectively) do not authorize requests using standard usernames/passwords; they authenticate solely based on device IMEI.
- **TCP (Codec 8)**: If possible, restrict access to `INGEST_CODEC8_PORT` on your firewall (e.g. UFW) only to the IP range of your cellular SIM cards, or route them through a private VPN/WireGuard interface.
- **HTTP (OsmAnd)**: Always route HTTP endpoints through Traefik/HTTPS to guarantee transport layer encryption (TLS).

### B. Rate Limiting
The `/share/{token}` public view endpoints are protected by slowapi rate limiters (by default: 30 requests/minute, 300 requests/hour per IP). Ensure your reverse proxy passes the correct client IP header (`X-Forwarded-For` or `X-Real-IP`) so limits are applied per remote client rather than to the gateway.

### C. Public Share Hardening & Redacted Logs
- TrackMy redacts raw shared-link paths in its API application logs.
- The Nginx configuration templates for the frontend are pre-configured to suppress request logging for public-share locations (`/api/share/*`) to maintain the secrecy of active tokens.

---

## 7. Backups and Database Maintenance

Location histories accumulate irreplaceable travel records. Back up your dataset regularly.

### SQLite Backups (Automatic & Consistent)
TrackMy includes an integrated backup utility that creates consistent, online backups of SQLite without locking operations:
```bash
docker compose run --rm api python scripts/backup_db.py
```
This utility automatically detects and hot-copies the central `identity.db` and all individual `tenant_*.db` user databases to `/data/backups/hourly/`, `/data/backups/daily/`, etc., executing vacuum cycles and rotating old snapshots automatically.

**Recommended Crontab Configuration:**
Install a cronjob on the Docker host to back up your database every night at midnight:
```cron
0 0 * * * cd /opt/trackmy && /usr/bin/docker compose run --rm api python scripts/backup_db.py > /dev/null 2>&1
```

---

## 8. Troubleshooting & Diagnostics

### Viewing Logs
TrackMy services use standardized JSON or clean structured logs depending on configuration.
```bash
# View backend API logs
docker compose logs -f api

# View ingest receiver logs
docker compose logs -f ingest
```

### Resetting Passwords
If an administrator is locked out, reset their credentials using the CLI tool:
```bash
docker compose run --rm api python -m tracker_core.cli.manage reset-password \
  --email you@example.com --password "your-secure-password"
```
This action automatically invalidates all active sessions by rotating the user's secret token version.
