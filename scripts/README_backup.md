# Database Backup (`backup_db.py`)

GFS-style backup script for Buteo. Works with both SQLite and PostgreSQL —
detected automatically from `DATABASE_URL` (same logic as the app).

## Retention

| Tier    | Location         | Filename example                  | Kept      |
|---------|------------------|-----------------------------------|-----------|
| Hourly  | `hourly/`        | `identity_2026-05-12_14-00.db`, `uploads_2026-05-12_14-00.tar` | 7 days    |
| Daily   | `daily/`         | `identity_2026-05-12.db`, `uploads_2026-05-12.tar`              | 30 days   |
| Weekly  | `weekly/`        | `identity_2026-W19.db`, `uploads_2026-W19.tar`                | forever   |

PostgreSQL dumps use `.pgdump` instead of `.db`. Media uploads are archived into uncompressed `.tar` files (avoiding CPU overhead since images/videos are already compressed).

## Setup

### 1. Configure `.env`

Set these in the repo-root `.env` (script loads it automatically):

```env
DATA_DIR=/absolute/path/to/data
# DATABASE_URL is derived automatically from DATA_DIR for SQLite.
# Only needed for Postgres or a non-default SQLite path:
# DATABASE_URL=postgresql+asyncpg://tracker:password@localhost:5432/tracker
# POSTGRES_USER=tracker
# POSTGRES_PASSWORD=secret
# POSTGRES_DB=tracker
# DB_HOST=localhost
# DB_PORT=5432
```

Layout inside `DATA_DIR`:
```
DATA_DIR/
  identity.db         ← Central identity database
  tntfoo.db       ← Tenant "foo" private database
  tntbar.db       ← Tenant "bar" private database
  backups/
    hourly/
    daily/
    weekly/
  uploads/            ← User media (automatically backed up)
    <user_id>/
```

### 2. Create the venv

```bash
cd /path/to/Buteo/scripts
python3 -m venv .venv
.venv/bin/pip install -r requirements_backup.txt
```

### 3. Dry run (verify before scheduling)

```bash
/path/to/Buteo/scripts/.venv/bin/python \
    /path/to/Buteo/scripts/backup_db.py --dry-run
```

### 4. Schedule with cron (every hour)

```bash
crontab -e
```

Add:

```cron
0 * * * * /path/to/Buteo/scripts/.venv/bin/python \
    /path/to/Buteo/scripts/backup_db.py \
    >> /var/log/tracker-backup.log 2>&1
```

The script reads `.env` from the repo root automatically and derives `BACKUP_DIR` from `DATA_DIR/backups` — no extra env wrangling in cron.

## Restore — SQLite

```bash
# Stop the app first, then:
cp "$DATA_DIR/backups/daily/core_2026-05-12.db" "$DATA_DIR/core.db"
# Restart the app.
```

## Restore — PostgreSQL

```bash
pg_restore --clean --if-exists \
    --host=localhost --port=5432 \
    --username=tracker --dbname=tracker \
    backups/daily/tracker_2026-05-12.pgdump
```

## Sync to remote (optional)

```bash
rsync -az "$BACKUP_DIR"/ remote-host:/backups/tracker/
```

Add to cron after the backup step.
