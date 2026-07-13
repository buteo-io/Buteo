"""CLI for user/device management under multi-tenant registry. Run: `python -m tracker_core.cli.manage <cmd>`."""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path

import click
from sqlalchemy import select

from tracker_core.custom_logger import configure_logging
from tracker_core.features import VALID_FEATURES, Feature
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.core_db import init_core_db as init_db
from tracker_core.store.identity_db import (
    GPSDevice,
    IdentitySessionLocal,
    Tenant,
    init_identity_db,
)
from tracker_core.store.models import Device, Entity, User
from tracker_core.store.security import hash_password
from tracker_core.store.tenant_db_manager import current_tenant_id, tenant_db_manager


def _run(coro):
    return asyncio.run(coro)


@click.group()
def cli() -> None:
    """Tracker management CLI."""
    configure_logging(AppConfig.log_level, debug=AppConfig.debug)


@cli.command("init-db")
@click.option("--tenant-id", help="Migrate a specific tenant. If omitted, migrates ALL active tenants.")
def init_db_cmd(tenant_id: str | None) -> None:
    """Run alembic migrations on identity and tenant databases. Idempotent."""

    async def _():
        await init_identity_db()
        if tenant_id:
            url = tenant_db_manager.get_tenant_url(tenant_id)
            click.echo(f"Migrating tenant {tenant_id}...")
            await init_db(url)
        else:
            click.echo("No tenant-id specified. Migrating ALL active tenant databases...")
            async with IdentitySessionLocal() as id_s:
                tenants = (await id_s.scalars(select(Tenant).where(Tenant.is_active))).all()
            for t in tenants:
                url = tenant_db_manager.get_tenant_url(t.tenant_id)
                click.echo(f"Migrating tenant {t.tenant_id}...")
                await init_db(url)
        click.echo("ok")

    _run(_())


@cli.command("create-user")
@click.option("--email", required=True)
@click.option("--password", required=True)
@click.option("--tenant-id", help="Tenant ID. Generates from email prefix if omitted.")
def create_user(email: str, password: str, tenant_id: str | None) -> None:
    """Register tenant in identity DB, run schema, and create local user inside tenant DB."""

    async def _():
        await init_identity_db()
        norm = email.strip().lower()
        if len(password) < 12:
            raise click.ClickException("password must be at least 12 chars")

        # Resolve/generate tenant_id
        target_tenant_id = tenant_id

        async with IdentitySessionLocal() as id_s:
            if not target_tenant_id:
                import uuid

                while True:
                    candidate = str(uuid.uuid4())
                    existing = await id_s.scalar(select(Tenant).where(Tenant.tenant_id == candidate))
                    if not existing:
                        target_tenant_id = candidate
                        break
            else:
                existing_tenant = await id_s.scalar(select(Tenant).where(Tenant.tenant_id == target_tenant_id))
                if existing_tenant:
                    raise click.ClickException(f"tenant already exists: {target_tenant_id}")

            existing_email = await id_s.scalar(select(Tenant).where(Tenant.email == norm))
            if existing_email:
                raise click.ClickException(f"email already registered: {norm}")

            tenant = Tenant(
                tenant_id=target_tenant_id,
                email=norm,
                password_hash=hash_password(password),
                database_type="sqlite",
                database_name=f"tnt{target_tenant_id}.db",
                features=[Feature.CAN_WRITE],
            )
            id_s.add(tenant)
            await id_s.commit()

        # Bootstrap tenant's schema
        tenant_url = tenant_db_manager.get_tenant_url(target_tenant_id)
        await init_db(tenant_url)

        # Create user + entity in tenant database
        current_tenant_id.set(target_tenant_id)
        async with SessionLocal() as s:
            existing_user = await s.scalar(select(User).where(User.email == norm))
            if existing_user:
                raise click.ClickException(f"user already exists: {norm}")

            u = User(email=norm)
            s.add(u)
            await s.flush()
            ent = Entity(user_id=u.id, type="tracker", name="My Tracker")
            s.add(ent)
            await s.commit()
            click.echo(
                f"created user id={u.id} public_id={u.public_id} email={u.email} "
                f"default_entity_id={ent.public_id} in tenant {target_tenant_id}",
            )

    _run(_())


@cli.command("reset-password")
@click.option("--email", required=True)
@click.option("--password", required=True)
def reset_password(email: str, password: str) -> None:
    """Reset password of tenant in identity DB and sync to tenant user row."""

    async def _():
        norm = email.strip().lower()
        if len(password) < 12:
            raise click.ClickException("password must be at least 12 chars")

        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == norm))
            if not tenant:
                raise click.ClickException("tenant not found")

            tenant.password_hash = hash_password(password)
            tenant.token_version = (tenant.token_version or 0) + 1
            await id_s.commit()

        click.echo("ok (existing sessions invalidated)")

    _run(_())


@cli.command("create-device")
@click.option("--email", required=True, help="owner email")
@click.option("--imei", required=True)
@click.option("--name", required=True)
@click.option("--entity-name", help="associated entity name")
def create_device(email: str, imei: str, name: str, entity_name: str | None = None) -> None:
    """Register device in identity DB and create local device row inside tenant DB."""

    async def _():
        norm = email.strip().lower()
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == norm))
            if not tenant:
                raise click.ClickException("tenant not found")

            # 1. Register device routing in identity DB
            existing_gps = await id_s.scalar(select(GPSDevice).where(GPSDevice.imei == imei))
            if existing_gps:
                raise click.ClickException(f"device imei registered to tenant: {existing_gps.tenant_id}")

            gps_device = GPSDevice(imei=imei, tenant_id=tenant.tenant_id)
            id_s.add(gps_device)
            await id_s.commit()
            tenant_id = tenant.tenant_id

        # 2. Add device metadata to tenant database
        current_tenant_id.set(tenant_id)
        async with SessionLocal() as s:
            u = await s.scalar(select(User).where(User.email == norm))
            if not u:
                raise click.ClickException(f"local user {norm} not found inside tenant DB")

            if entity_name:
                ent = await s.scalar(select(Entity).where(Entity.user_id == u.id, Entity.name == entity_name))
                if not ent:
                    raise click.ClickException(f"entity {entity_name!r} not found for user {norm}")
            else:
                ent = await s.scalar(select(Entity).where(Entity.user_id == u.id).order_by(Entity.id))
                if not ent:
                    ent = Entity(user_id=u.id, type="tracker", name="My Tracker")
                    s.add(ent)
                    await s.flush()

            name_clash = await s.scalar(
                select(Device).where(Device.entity_id == ent.id, Device.name == name),
            )
            if name_clash:
                raise click.ClickException(f"entity {ent.name} already has a device named {name!r}")

            existing_device = await s.scalar(select(Device).where(Device.imei == imei))
            if existing_device:
                raise click.ClickException(f"device with imei already exists: {imei}")

            d = Device(entity_id=ent.id, imei=imei, name=name)
            s.add(d)
            await s.commit()
            click.echo(
                f"created device id={d.id} public_id={d.public_id} imei={d.imei} "
                f"name={d.name} entity={ent.name} in tenant {tenant_id}",
            )

    _run(_())


@cli.command("revoke-device")
@click.option("--imei", required=True)
def revoke_device(imei: str) -> None:
    """Revoke device in tenant DB and remove routing from identity DB."""

    async def _():
        async with IdentitySessionLocal() as id_s:
            gps = await id_s.scalar(select(GPSDevice).where(GPSDevice.imei == imei))
            if not gps:
                raise click.ClickException("device routing not found in identity DB")
            tenant_id = gps.tenant_id
            await id_s.delete(gps)
            await id_s.commit()

        # Revoke inside tenant database
        current_tenant_id.set(tenant_id)
        async with SessionLocal() as s:
            d = await s.scalar(select(Device).where(Device.imei == imei))
            if d:
                d.revoked_at = datetime.now(tz=UTC)
                await s.commit()
            click.echo(f"revoked device imei={imei} and removed identity routing")

    _run(_())


@cli.command("deactivate-user")
@click.option("--email", required=True)
def deactivate_user(email: str) -> None:
    """Deactivate tenant in identity DB and sync to tenant user row."""

    async def _():
        norm = email.strip().lower()
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == norm))
            if not tenant:
                raise click.ClickException("tenant not found")
            tenant.is_active = False
            tenant.token_version = (tenant.token_version or 0) + 1
            await id_s.commit()
            tenant_id = tenant.tenant_id

        current_tenant_id.set(tenant_id)
        async with SessionLocal() as s:
            u = await s.scalar(select(User).where(User.email == norm))
            if u:
                u.is_active = False
                u.token_version = (u.token_version or 0) + 1
                await s.commit()
            click.echo(f"deactivated user {norm}")

    _run(_())


@cli.command("activate-user")
@click.option("--email", required=True)
def activate_user(email: str) -> None:
    """Activate tenant in identity DB and sync to tenant user row."""

    async def _():
        norm = email.strip().lower()
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == norm))
            if not tenant:
                raise click.ClickException("tenant not found")
            tenant.is_active = True
            await id_s.commit()
            tenant_id = tenant.tenant_id

        current_tenant_id.set(tenant_id)
        async with SessionLocal() as s:
            u = await s.scalar(select(User).where(User.email == norm))
            if u:
                u.is_active = True
                await s.commit()
            click.echo(f"activated user {norm}")

    _run(_())


@cli.command("list-users")
def list_users() -> None:
    """List registered tenants in identity DB."""

    async def _():
        async with IdentitySessionLocal() as id_s:
            rows = (await id_s.scalars(select(Tenant).order_by(Tenant.id))).all()
            for t in rows:
                flag = "" if t.is_active else " INACTIVE"
                click.echo(f"{t.id}\t{t.tenant_id}\t{t.email}{flag}")

    _run(_())


@cli.command("list-devices")
def list_devices() -> None:
    """List registered devices in identity DB."""

    async def _():
        async with IdentitySessionLocal() as id_s:
            rows = (await id_s.scalars(select(GPSDevice).order_by(GPSDevice.id))).all()
            for d in rows:
                click.echo(f"{d.id}\t{d.imei}\t{d.tenant_id}")

    _run(_())


@cli.command("delete-tenant")
@click.option("--tenant-id", required=True)
def delete_tenant(tenant_id: str) -> None:
    async def _():
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))
            if not tenant:
                raise click.ClickException(f"tenant not found: {tenant_id}")
            await id_s.delete(tenant)
            await id_s.commit()

        await tenant_db_manager.clear_cache()

        db_type = AppConfig.database_type.strip().lower()
        if db_type == "sqlite" and AppConfig.data_dir:
            db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
            wal_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db-wal"
            shm_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db-shm"
            db_file.unlink(missing_ok=True)
            wal_file.unlink(missing_ok=True)
            shm_file.unlink(missing_ok=True)

        data_dir = AppConfig.data_dir or "/data"
        uploads_dir = Path(data_dir) / "uploads" / tenant_id
        if uploads_dir.exists() and uploads_dir.is_dir():
            shutil.rmtree(uploads_dir)

        click.echo("ok")

    _run(_())


@cli.group("features")
def features_group() -> None:
    """Manage tenant feature flags."""


@features_group.command("available")
def list_available_features() -> None:
    """List all valid feature flag names."""
    click.echo("Available feature flags:")
    for name in sorted(VALID_FEATURES):
        click.echo(f"  {name}")


@features_group.command("list")
@click.option("--email", required=True, help="Tenant owner email")
def list_features(email: str) -> None:
    """List active feature flags for a tenant."""

    async def _():
        email_normalized = email.strip().lower()
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == email_normalized))
            if not tenant:
                raise click.ClickException("tenant not found")

            feat_list = tenant.features or []
            click.echo(f"Active features for {tenant.email} (tenant={tenant.tenant_id}):")
            if not feat_list:
                click.echo("  (none)")
            for f in feat_list:
                suffix = "" if f in VALID_FEATURES else "  (unknown flag)"
                click.echo(f"  - {f}{suffix}")

    _run(_())


@features_group.command("grant")
@click.option("--email", required=True, help="Tenant owner email")
@click.option("--feature", required=True, help="Feature name to grant")
def grant_feature(email: str, feature: str) -> None:
    """Grant a feature flag to a tenant. Invalidates old sessions."""

    async def _():
        email_normalized = email.strip().lower()
        feature_normalized = feature.strip()
        if feature_normalized not in VALID_FEATURES:
            raise click.ClickException(
                f"Unknown feature '{feature_normalized}'. Valid flags: {', '.join(sorted(VALID_FEATURES))}",
            )
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == email_normalized))
            if not tenant:
                raise click.ClickException("tenant not found")

            current_feats = list(tenant.features or [])
            if feature_normalized in current_feats:
                click.echo(f"Feature '{feature_normalized}' already granted.")
                return

            current_feats.append(feature_normalized)
            tenant.features = current_feats
            tenant.token_version = (tenant.token_version or 0) + 1
            await id_s.commit()
            click.echo(f"Granted '{feature_normalized}' to {tenant.email}. Session tokens invalidated.")

    _run(_())


@features_group.command("revoke")
@click.option("--email", required=True, help="Tenant owner email")
@click.option("--feature", required=True, help="Feature name to revoke")
def revoke_feature(email: str, feature: str) -> None:
    """Revoke a feature flag from a tenant. Invalidates old sessions."""

    async def _():
        email_normalized = email.strip().lower()
        feature_normalized = feature.strip()
        if feature_normalized not in VALID_FEATURES:
            raise click.ClickException(
                f"Unknown feature '{feature_normalized}'. Valid flags: {', '.join(sorted(VALID_FEATURES))}",
            )
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == email_normalized))
            if not tenant:
                raise click.ClickException("tenant not found")

            current_feats = list(tenant.features or [])
            if feature_normalized not in current_feats:
                click.echo(f"Feature '{feature_normalized}' not present.")
                return

            current_feats.remove(feature_normalized)
            tenant.features = current_feats
            tenant.token_version = (tenant.token_version or 0) + 1
            await id_s.commit()
            click.echo(f"Revoked '{feature_normalized}' from {tenant.email}. Session tokens invalidated.")

    _run(_())


if __name__ == "__main__":
    cli()
