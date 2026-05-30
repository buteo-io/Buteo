"""GFS-style database backup for trackmy-core.

Supports SQLite and PostgreSQL. Detection mirrors store/db.py:
DATABASE_URL starting with "sqlite" -> SQLite, anything else -> Postgres.

Directory layout:
    DATA_DIR/core.db                                  (SQLite DB)
    DATA_DIR/backups/hourly/   core_YYYY-MM-DD_HH-MM.db[dump]   kept 7 days
    DATA_DIR/backups/daily/    core_YYYY-MM-DD.db[dump]          kept 30 days
    DATA_DIR/backups/weekly/   core_YYYY-Www.db[dump]            kept forever

Each run:
  1. Write a fresh backup into hourly/
  2. Promote to daily/ if today has no entry yet
  3. Promote to weekly/ if this ISO-week has no entry yet
  4. Prune hourly/ (>7 days) and daily/ (>30 days)

Usage (SQLite, DATA_DIR set):
    DATA_DIR=/absolute/path/to/data python scripts/backup_db.py

Usage (Postgres):
    DATABASE_URL=postgresql+asyncpg://... \\
    POSTGRES_USER=tracker POSTGRES_PASSWORD=secret \\
    POSTGRES_DB=tracker DB_HOST=localhost DB_PORT=5432 \\
    python scripts/backup_db.py

Dry-run (no writes, no deletes):
    DATA_DIR=/absolute/path/to/data python scripts/backup_db.py --dry-run

Requires the venv from scripts/.venv (see scripts/README_backup.md).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HOURLY_KEEP = timedelta(days=7)
DAILY_KEEP = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _log(msg: str) -> None:
    print(f"{_now().isoformat(timespec='seconds')} {msg}", flush=True)


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def _sqlite_db_path(database_url: str) -> Path:
    """Extract filesystem path from a sqlite URL (any aiosqlite/pysqlite variant)."""
    raw = database_url.split("://", 1)[1]
    if raw.startswith("/"):
        return Path("/" + raw.lstrip("/"))
    return Path(raw)


def get_sqlite_dbs_to_backup(
    data_dir_env: str | None, database_url: str
) -> list[tuple[str, Path]]:
    """Return list of (db_name, db_path) SQLite files to back up."""
    dbs = []
    if data_dir_env:
        base_dir = Path(data_dir_env)
    else:
        try:
            base_path = _sqlite_db_path(database_url)
            base_dir = base_path.parent
        except Exception:
            base_dir = Path(".")

    # Canonical identity.db and core.db (if old/legacy single-DB setup)
    for name in ("identity", "core"):
        db_file = base_dir / f"{name}.db"
        if db_file.exists():
            dbs.append((name, db_file))

    # All dynamic tenant databases (tnt{tenant_id}.db)
    for p in base_dir.glob("tnt*.db"):
        dbs.append((p.stem, p))

    # Ensure database_url database is included if it exists and wasn't added
    if database_url:
        try:
            url_db = _sqlite_db_path(database_url)
            if url_db.exists() and url_db not in [path for _, path in dbs]:
                dbs.append((url_db.stem, url_db))
        except Exception:
            pass

    return dbs


def backup_sqlite(
    db_path: Path, backup_dir: Path, stem_prefix: str, dry_run: bool
) -> Path:
    """Hot-copy the SQLite DB into backup_dir/hourly/<db_name>_<YYYY-MM-DD_HH-MM>.db."""
    dest = backup_dir / "hourly" / f"{db_path.stem}_{stem_prefix}.db"
    _log(f"sqlite backup  {db_path} -> {dest}")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        src_conn = sqlite3.connect(str(db_path))
        dst_conn = sqlite3.connect(str(dest))
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
    return dest


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------


def get_postgres_dbs_to_backup() -> list[str]:
    """Retrieve list of PostgreSQL databases matching our multi-tenant convention."""
    user = os.environ.get("POSTGRES_USER", "tracker")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    default_db = os.environ.get("POSTGRES_DB", "tracker")

    # Connect to PostgreSQL pg_database to find matching databases
    env = {**os.environ, "PGPASSWORD": password}
    query = (
        f"SELECT datname FROM pg_database "
        f"WHERE datname LIKE 'tracker_tenant_%' OR datname = 'tracker_identity' OR datname = '{default_db}';"
    )
    cmd = [
        "psql",
        f"--host={host}",
        f"--port={port}",
        f"--username={user}",
        f"--dbname={default_db}",
        "-t",
        "-A",
        f"--command={query}",
    ]
    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, check=True
        )
        db_names = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
        if db_names:
            return db_names
    except Exception as exc:
        _log(f"Warning: Could not list databases via psql: {exc}")

    # Fallback default names if listing query fails
    return ["tracker_identity", default_db]


def backup_postgres(
    db_name: str, backup_dir: Path, stem_prefix: str, dry_run: bool
) -> Path:
    """Dump Postgres DB via pg_dump --format=custom into backup_dir/hourly/<db_name>_<stem>.pgdump."""
    user = os.environ.get("POSTGRES_USER", "tracker")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")

    dest = backup_dir / "hourly" / f"{db_name}_{stem_prefix}.pgdump"
    _log(f"postgres backup  {user}@{host}:{port}/{db_name} -> {dest}")

    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PGPASSWORD": password}
        cmd = [
            "pg_dump",
            "--format=custom",
            f"--host={host}",
            f"--port={port}",
            f"--username={user}",
            f"--dbname={db_name}",
            f"--file={dest}",
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            _log(f"pg_dump failed:\n{result.stderr}")
            raise RuntimeError(f"pg_dump failed for {db_name}")
    return dest


# ---------------------------------------------------------------------------
# GFS promote + prune
# ---------------------------------------------------------------------------


def _ext(is_sqlite: bool) -> str:
    return ".db" if is_sqlite else ".pgdump"


def _files_in(directory: Path, ext: str) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob(f"*{ext}"))


def promote_daily(
    backup_dir: Path, today: datetime, ext: str, dry_run: bool
) -> None:
    """Copy the newest hourly backup for each prefix into daily/ if today has no entry."""
    hourly_dir = backup_dir / "hourly"
    daily_dir = backup_dir / "daily"

    hourly_files = _files_in(hourly_dir, ext)
    if not hourly_files:
        _log(f"no hourly {ext} backups to promote to daily")
        return

    by_db: dict[str, list[Path]] = {}
    for f in hourly_files:
        stem = f.stem
        if len(stem) > 17 and stem[-17] == "_":
            db_name = stem[:-17]
            by_db.setdefault(db_name, []).append(f)

    for db_name, files in by_db.items():
        day_stem = f"{db_name}_{today.strftime('%Y-%m-%d')}"
        dest = daily_dir / f"{day_stem}{ext}"

        if dest.exists():
            _log(f"daily already exists for {db_name}: {dest.name}")
            continue

        src = files[-1]
        _log(f"promote daily  {src.name} -> {dest.name}")
        if not dry_run:
            daily_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def promote_weekly(
    backup_dir: Path, today: datetime, ext: str, dry_run: bool
) -> None:
    """Copy the newest daily backup for each prefix into weekly/ if this ISO-week has no entry."""
    daily_dir = backup_dir / "daily"
    weekly_dir = backup_dir / "weekly"

    daily_files = _files_in(daily_dir, ext)
    if not daily_files:
        _log(f"no daily {ext} backups to promote to weekly")
        return

    by_db: dict[str, list[Path]] = {}
    for f in daily_files:
        stem = f.stem
        if len(stem) > 11 and stem[-11] == "_":
            db_name = stem[:-11]
            by_db.setdefault(db_name, []).append(f)

    iso_year, iso_week, _ = today.isocalendar()
    for db_name, files in by_db.items():
        week_stem = f"{db_name}_{iso_year}-W{iso_week:02d}"
        dest = weekly_dir / f"{week_stem}{ext}"

        if dest.exists():
            _log(f"weekly already exists for {db_name}: {dest.name}")
            continue

        src = files[-1]
        _log(f"promote weekly  {src.name} -> {dest.name}")
        if not dry_run:
            weekly_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def prune(backup_dir: Path, ext: str, now: datetime, dry_run: bool) -> None:
    """Delete hourly files >7 days old and daily files >30 days old."""
    cutoffs = {
        "hourly": now - HOURLY_KEEP,
        "daily": now - DAILY_KEEP,
    }

    for tier, cutoff in cutoffs.items():
        for f in _files_in(backup_dir / tier, ext):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                _log(f"prune {tier}  {f.name}  (mtime {mtime.date()})")
                if not dry_run:
                    f.unlink()


def backup_uploads(
    uploads_dir: Path, backup_dir: Path, stem_prefix: str, dry_run: bool
) -> Path | None:
    """Pack uploads folder into backup_dir/hourly/uploads_<YYYY-MM-DD_HH-MM>.tar.

    No compression is used because uploaded media files (images, videos) are already
    heavily compressed formats (JPEG, PNG, MP4), making compression CPU-heavy and wasteful.
    """
    if not uploads_dir.exists():
        _log(f"uploads directory {uploads_dir} does not exist, skipping.")
        return None

    has_files = any(uploads_dir.iterdir()) if uploads_dir.is_dir() else False
    if not has_files:
        _log(f"uploads directory {uploads_dir} is empty, skipping.")
        return None

    dest = backup_dir / "hourly" / f"uploads_{stem_prefix}.tar"
    _log(f"uploads backup  {uploads_dir} -> {dest}")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest, "w") as tar:
            for item in uploads_dir.iterdir():
                tar.add(item, arcname=item.name)
    return dest


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="GFS-style DB backup for trackmy-core")
    ap.add_argument(
        "--backup-dir",
        default=os.environ.get("BACKUP_DIR"),
        help="Root backup directory (env: BACKUP_DIR)",
    )
    ap.add_argument(
        "--db",
        default=None,
        help="Path to SQLite .db file (overrides DATABASE_URL path; ignored for Postgres)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without writing or deleting anything",
    )
    args = ap.parse_args()

    data_dir = os.environ.get("DATA_DIR")

    backup_dir_raw = args.backup_dir
    if not backup_dir_raw:
        if data_dir:
            backup_dir_raw = str(Path(data_dir) / "backups")
    if not backup_dir_raw:
        _log("ERROR: --backup-dir, BACKUP_DIR, or DATA_DIR env var required")
        return 1

    backup_dir = Path(backup_dir_raw)
    database_url = os.environ.get("DATABASE_URL", "")

    # Determine DB type: explicit URL takes precedence; DATA_DIR alone implies SQLite.
    if database_url:
        is_sqlite = database_url.startswith("sqlite")
    elif data_dir:
        is_sqlite = True
        database_url = f"sqlite+aiosqlite:///{data_dir}/core.db"
    else:
        _log("ERROR: DATABASE_URL or DATA_DIR env var required")
        return 1

    now = _now()
    stem_hourly = now.strftime("%Y-%m-%d_%H-%M")

    if args.dry_run:
        _log("DRY RUN — no files will be written or deleted")

    try:
        if is_sqlite:
            dbs = get_sqlite_dbs_to_backup(data_dir, database_url)
            if not dbs:
                _log("ERROR: No SQLite databases found to backup")
                return 1
            for db_name, db_path in dbs:
                backup_sqlite(db_path, backup_dir, stem_hourly, args.dry_run)
        else:
            db_names = get_postgres_dbs_to_backup()
            for db_name in db_names:
                backup_postgres(db_name, backup_dir, stem_hourly, args.dry_run)

        # Back up uploads folder if it exists
        if data_dir:
            uploads_dir = Path(data_dir) / "uploads"
        else:
            try:
                base_path = _sqlite_db_path(database_url)
                uploads_dir = base_path.parent / "uploads"
            except Exception:
                uploads_dir = Path("uploads")

        backup_uploads(uploads_dir, backup_dir, stem_hourly, args.dry_run)

        db_ext = _ext(is_sqlite)
        promote_daily(backup_dir, now, db_ext, args.dry_run)
        promote_weekly(backup_dir, now, db_ext, args.dry_run)
        prune(backup_dir, db_ext, now, args.dry_run)

        promote_daily(backup_dir, now, ".tar", args.dry_run)
        promote_weekly(backup_dir, now, ".tar", args.dry_run)
        prune(backup_dir, ".tar", now, args.dry_run)

    except Exception as exc:
        _log(f"ERROR: {exc}")
        return 1

    _log("backup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
