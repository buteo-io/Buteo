"""backfill can_write feature flag for all existing tenants

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, features FROM tenants")).fetchall()
    for row_id, raw in rows:
        try:
            feats = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (TypeError, ValueError):
            feats = []
        if "can_write" not in feats:
            feats.append("can_write")
            conn.execute(
                sa.text("UPDATE tenants SET features = :f WHERE id = :id"),
                {"f": json.dumps(feats), "id": row_id},
            )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, features FROM tenants")).fetchall()
    for row_id, raw in rows:
        try:
            feats = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (TypeError, ValueError):
            feats = []
        if "can_write" in feats:
            feats.remove("can_write")
            conn.execute(
                sa.text("UPDATE tenants SET features = :f WHERE id = :id"),
                {"f": json.dumps(feats), "id": row_id},
            )
