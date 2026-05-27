"""initial consolidated identity schema

Revision ID: 0001
Revises:
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("database_type", sa.String(length=10), nullable=False),
        sa.Column("database_name", sa.String(length=255), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("features", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("email = lower(email)", name="tenants_email_lowercase"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenants_email"), "tenants", ["email"], unique=True)
    op.create_index(op.f("ix_tenants_tenant_id"), "tenants", ["tenant_id"], unique=True)
    op.create_table(
        "gps_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("imei", sa.String(length=30), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gps_devices_imei"), "gps_devices", ["imei"], unique=True)
    op.create_index(op.f("ix_gps_devices_tenant_id"), "gps_devices", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gps_devices_tenant_id"), table_name="gps_devices")
    op.drop_index(op.f("ix_gps_devices_imei"), table_name="gps_devices")
    op.drop_table("gps_devices")
    op.drop_index(op.f("ix_tenants_tenant_id"), table_name="tenants")
    op.drop_index(op.f("ix_tenants_email"), table_name="tenants")
    op.drop_table("tenants")
