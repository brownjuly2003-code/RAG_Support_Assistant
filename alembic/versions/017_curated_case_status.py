"""curated case freshness status

Revision ID: 017
Revises: 016
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curated_case_status",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="fresh"),
        sa.Column("staleness_reason", sa.String(length=64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_curated_case_status_tenant_id",
        "curated_case_status",
        ["tenant_id"],
    )
    op.create_index(
        "ix_curated_case_status_status",
        "curated_case_status",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curated_case_status_status",
        table_name="curated_case_status",
    )
    op.drop_index(
        "ix_curated_case_status_tenant_id",
        table_name="curated_case_status",
    )
    op.drop_table("curated_case_status")
