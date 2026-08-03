"""ingestion job upload idempotency fields

Revision ID: 021
Revises: 020
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("source_ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_ingestion_jobs_tenant_idempotency_key_hash",
        "ingestion_jobs",
        ["tenant_id", "idempotency_key_hash"],
        unique=True,
        postgresql_where=sa.text("idempotency_key_hash IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ingestion_jobs_tenant_idempotency_key_hash",
        table_name="ingestion_jobs",
    )
    op.drop_column("ingestion_jobs", "source_ready_at")
    op.drop_column("ingestion_jobs", "payload_fingerprint")
    op.drop_column("ingestion_jobs", "idempotency_key_hash")
