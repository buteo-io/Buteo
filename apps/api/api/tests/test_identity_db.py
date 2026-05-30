"""Tests for the Identity Database models and registry migrations."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from tracker_core.store.identity_db import (
    GPSDevice,
    IdentitySessionLocal,
    Tenant,
    init_identity_db,
)
from tracker_core.store.security import hash_password


@pytest.mark.asyncio
async def test_identity_db_initialization() -> None:
    """Verify identity database updates successfully to head."""
    await init_identity_db()


@pytest.mark.asyncio
async def test_identity_tenant_lifecycle() -> None:
    """Verify Tenant model can be created, updated, and deleted."""
    await init_identity_db()
    async with IdentitySessionLocal() as session:
        # Clean existing test tenants
        await session.execute(delete(Tenant).where(Tenant.tenant_id == "test-tenant-1"))
        await session.commit()

        # Create tenant
        tenant = Tenant(
            tenant_id="test-tenant-1",
            email="test-tenant@example.com",
            password_hash=hash_password("testpass123"),
            database_type="sqlite",
            database_name="data/tenant_test-tenant-1.db",
        )
        session.add(tenant)
        await session.commit()

        # Query tenant
        stmt = select(Tenant).where(Tenant.tenant_id == "test-tenant-1")
        result = await session.execute(stmt)
        retrieved = result.scalar_one()
        assert retrieved.email == "test-tenant@example.com"
        assert retrieved.is_active is True
        assert retrieved.database_type == "sqlite"
        assert retrieved.database_name == "data/tenant_test-tenant-1.db"

        # Update tenant
        retrieved.is_active = False
        await session.commit()

        # Verify update
        result = await session.execute(stmt)
        updated = result.scalar_one()
        assert updated.is_active is False

        # Delete tenant
        await session.delete(updated)
        await session.commit()

        # Verify deleted
        result = await session.execute(stmt)
        assert result.scalar() is None


@pytest.mark.asyncio
async def test_identity_gps_device_cascade() -> None:
    """Verify that deleting a tenant cascades and deletes associated GPS devices."""
    await init_identity_db()
    async with IdentitySessionLocal() as session:
        # Clean existing test data
        await session.execute(
            delete(GPSDevice).where(GPSDevice.imei == "123456789012345")
        )
        await session.execute(
            delete(Tenant).where(Tenant.tenant_id == "test-tenant-route")
        )
        await session.commit()

        # Create tenant
        tenant = Tenant(
            tenant_id="test-tenant-route",
            email="route@example.com",
            password_hash=hash_password("pass123"),
            database_type="sqlite",
            database_name="data/tenant_route.db",
        )
        session.add(tenant)
        await session.commit()

        # Create GPS device
        device = GPSDevice(
            imei="123456789012345",
            tenant_id="test-tenant-route",
        )
        session.add(device)
        await session.commit()

        # Verify device can be retrieved
        stmt = select(GPSDevice).where(GPSDevice.imei == "123456789012345")
        res = await session.execute(stmt)
        retrieved_device = res.scalar_one()
        assert retrieved_device.tenant_id == "test-tenant-route"

        # Delete tenant
        await session.delete(tenant)
        await session.commit()

        # Verify device was deleted via foreign key cascade
        res = await session.execute(stmt)
        assert res.scalar() is None


@pytest.mark.asyncio
async def test_identity_tenant_unique_constraints() -> None:
    """Verify that unique constraints are correctly enforced."""
    await init_identity_db()
    async with IdentitySessionLocal() as session:
        # Clean existing
        await session.execute(
            delete(Tenant).where(Tenant.tenant_id.in_(["tenant-a", "tenant-b"]))
        )
        await session.commit()

        tenant_a = Tenant(
            tenant_id="tenant-a",
            email="unique@example.com",
            password_hash="pw123",
            database_type="sqlite",
            database_name="data/tenant_a.db",
        )
        session.add(tenant_a)
        await session.commit()

        # Duplicate email
        tenant_b_dup_email = Tenant(
            tenant_id="tenant-b",
            email="unique@example.com",
            password_hash="pw456",
            database_type="sqlite",
            database_name="data/tenant_b.db",
        )
        session.add(tenant_b_dup_email)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Duplicate tenant_id
        tenant_b_dup_id = Tenant(
            tenant_id="tenant-a",
            email="other@example.com",
            password_hash="pw456",
            database_type="sqlite",
            database_name="data/tenant_b.db",
        )
        session.add(tenant_b_dup_id)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Cleanup
        await session.delete(tenant_a)
        await session.commit()
