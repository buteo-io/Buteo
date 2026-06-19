"""Tests for the management CLI commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import delete, select
from tracker_core.cli.manage import cli
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.identity_db import IdentitySessionLocal, Tenant
from tracker_core.store.tenant_db_manager import tenant_db_manager


def test_create_user_with_generated_tenant_id() -> None:
    """Verify create-user command works and generates a tenant ID if omitted."""
    runner = CliRunner()
    email = "test-cli-gen@example.com"
    password = "password123456"

    async def setup():
        # Ensure clean state in identity database
        async with IdentitySessionLocal() as id_s:
            await id_s.execute(delete(Tenant).where(Tenant.email == email))
            await id_s.commit()
        await tenant_db_manager.clear_cache()

    asyncio.run(setup())

    # Run the CLI without --tenant-id option
    result = runner.invoke(
        cli,
        [
            "create-user",
            "--email",
            email,
            "--password",
            password,
        ],
    )

    assert result.exit_code == 0, f"CLI output: {result.output}"
    assert "created user id=" in result.output

    import re

    # Look for "in tenant <uuid>"
    match = re.search(
        r"in tenant ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
        result.output,
    )
    assert match is not None, f"Expected full UUID tenant ID in output: {result.output}"
    generated_id = match.group(1)

    async def verify_and_cleanup():
        # Query identity database to verify the generated tenant ID format
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == email))
            assert tenant is not None
            assert tenant.tenant_id == generated_id
            # clean up
            await id_s.delete(tenant)
            await id_s.commit()
            return generated_id

    asyncio.run(verify_and_cleanup())

    async def final_cleanup():
        # Clean up the generated tenant database
        await tenant_db_manager.clear_cache()

    asyncio.run(final_cleanup())

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{generated_id}.db"
        if db_file.exists():
            db_file.unlink()


def test_create_user_with_provided_tenant_id() -> None:
    """Verify create-user command works with a manually provided tenant ID."""
    runner = CliRunner()
    email = "test-cli-manual@example.com"
    password = "password123456"
    tenant_id = "manual-test-id"

    async def setup():
        # Ensure clean state in identity database
        async with IdentitySessionLocal() as id_s:
            await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
            await id_s.execute(delete(Tenant).where(Tenant.email == email))
            await id_s.commit()
        await tenant_db_manager.clear_cache()

    asyncio.run(setup())

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
        if db_file.exists():
            db_file.unlink()

    # Run the CLI with --tenant-id option
    result = runner.invoke(
        cli,
        [
            "create-user",
            "--email",
            email,
            "--password",
            password,
            "--tenant-id",
            tenant_id,
        ],
    )

    assert result.exit_code == 0, f"CLI output: {result.output}"
    assert f"in tenant {tenant_id}" in result.output

    async def verify_and_cleanup():
        # Query identity database to verify the tenant ID matches
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == email))
            assert tenant is not None
            assert tenant.tenant_id == tenant_id
            # clean up
            await id_s.delete(tenant)
            await id_s.commit()

    asyncio.run(verify_and_cleanup())

    async def final_cleanup():
        # Clean up the tenant database
        await tenant_db_manager.clear_cache()

    asyncio.run(final_cleanup())

    if AppConfig.database_type.strip().lower() == "sqlite" and AppConfig.data_dir:
        db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
        if db_file.exists():
            db_file.unlink()


def test_delete_tenant_command() -> None:
    runner = CliRunner()
    email = "test-delete-tenant@example.com"
    password = "password123456"
    tenant_id = "tenant-to-delete"

    async def setup():
        async with IdentitySessionLocal() as id_s:
            await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
            await id_s.execute(delete(Tenant).where(Tenant.email == email))
            await id_s.commit()
        await tenant_db_manager.clear_cache()

    asyncio.run(setup())

    db_file = Path(AppConfig.data_dir) / f"tnt{tenant_id}.db"
    if db_file.exists():
        db_file.unlink()

    result = runner.invoke(
        cli,
        [
            "create-user",
            "--email",
            email,
            "--password",
            password,
            "--tenant-id",
            tenant_id,
        ],
    )
    assert result.exit_code == 0

    uploads_dir = Path(AppConfig.data_dir) / "uploads" / tenant_id
    uploads_dir.mkdir(parents=True, exist_ok=True)
    dummy_file = uploads_dir / "test.txt"
    dummy_file.write_text("hello")

    assert db_file.exists()
    assert dummy_file.exists()

    result_delete = runner.invoke(
        cli,
        [
            "delete-tenant",
            "--tenant-id",
            tenant_id,
        ],
    )
    assert result_delete.exit_code == 0
    assert "ok" in result_delete.output

    assert not db_file.exists()
    assert not uploads_dir.exists()

    async def verify_deleted():
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(
                select(Tenant).where(Tenant.tenant_id == tenant_id)
            )
            assert tenant is None

    asyncio.run(verify_deleted())


def test_cli_features_management() -> None:
    """Verify that features list, grant, and revoke commands work correctly."""
    runner = CliRunner()
    email = "test-features-cli@example.com"
    password = "password123456"
    tenant_id = "test-feat-tnt"

    async def setup():
        async with IdentitySessionLocal() as id_s:
            await id_s.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
            await id_s.execute(delete(Tenant).where(Tenant.email == email))
            await id_s.commit()
        await tenant_db_manager.clear_cache()

    asyncio.run(setup())

    # 1. Create tenant/user
    result = runner.invoke(
        cli,
        [
            "create-user",
            "--email",
            email,
            "--password",
            password,
            "--tenant-id",
            tenant_id,
        ],
    )
    assert result.exit_code == 0

    # 2. List features (should have can_write by default)
    result_list = runner.invoke(cli, ["features", "list", "--email", email])
    assert result_list.exit_code == 0
    assert "can_write" in result_list.output

    # Get initial token version
    async def get_tenant_details():
        async with IdentitySessionLocal() as id_s:
            tenant = await id_s.scalar(select(Tenant).where(Tenant.email == email))
            assert tenant is not None
            return tenant.token_version, tenant.features

    initial_version, initial_feats = asyncio.run(get_tenant_details())
    assert initial_feats == ["can_write"]

    # 3. Reject unknown feature names
    result_bad = runner.invoke(
        cli,
        ["features", "grant", "--email", email, "--feature", "typo_flag"],
    )
    assert result_bad.exit_code != 0
    assert "Unknown feature" in result_bad.output
    assert "can_write" in result_bad.output  # valid names listed in error

    result_bad_revoke = runner.invoke(
        cli,
        ["features", "revoke", "--email", email, "--feature", "typo_flag"],
    )
    assert result_bad_revoke.exit_code != 0
    assert "Unknown feature" in result_bad_revoke.output

    # Token version must not have changed
    v_after_bad, _ = asyncio.run(get_tenant_details())
    assert v_after_bad == initial_version

    # 4. Revoke can_write (simulate pausing tenant)
    result_grant = runner.invoke(
        cli,
        ["features", "revoke", "--email", email, "--feature", "can_write"],
    )
    assert result_grant.exit_code == 0
    assert "Revoked 'can_write'" in result_grant.output

    # Verify revoked feature and bumped token version
    v_after_grant, feats_after_grant = asyncio.run(get_tenant_details())
    assert v_after_grant == initial_version + 1
    assert feats_after_grant == []

    # List features again — should show none
    result_list_2 = runner.invoke(cli, ["features", "list", "--email", email])
    assert result_list_2.exit_code == 0
    assert "(none)" in result_list_2.output

    # Revoking already revoked feature should be idempotent and not bump token version
    result_grant_again = runner.invoke(
        cli,
        ["features", "revoke", "--email", email, "--feature", "can_write"],
    )
    assert result_grant_again.exit_code == 0
    v_after_grant_again, _ = asyncio.run(get_tenant_details())
    assert v_after_grant_again == v_after_grant

    # 5. Re-grant can_write (restore access)
    result_revoke = runner.invoke(
        cli,
        ["features", "grant", "--email", email, "--feature", "can_write"],
    )
    assert result_revoke.exit_code == 0
    assert "Granted 'can_write'" in result_revoke.output

    # Verify restored feature and bumped token version
    v_after_revoke, feats_after_revoke = asyncio.run(get_tenant_details())
    assert v_after_revoke == v_after_grant + 1
    assert feats_after_revoke == ["can_write"]

    # Clean up
    runner.invoke(cli, ["delete-tenant", "--tenant-id", tenant_id])
