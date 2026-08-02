"""ingestion job leases and heartbeats

Revision ID: 020
Revises: 019
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("lease_token", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ingestion_jobs_status_lease_expires_at",
        "ingestion_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_jobs_status_lease_expires_at",
        table_name="ingestion_jobs",
    )
    op.drop_column("ingestion_jobs", "lease_expires_at")
    op.drop_column("ingestion_jobs", "heartbeat_at")
    op.drop_column("ingestion_jobs", "lease_token")
