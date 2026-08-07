"""ingestion job index publication lifecycle bind columns

Revision ID: 022
Revises: 021
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("index_active_collection", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("index_previous_collection", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("index_manifest_generation", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_ingestion_jobs_tenant_id_index_active_collection",
        "ingestion_jobs",
        ["tenant_id", "index_active_collection"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_jobs_tenant_id_index_active_collection",
        table_name="ingestion_jobs",
    )
    op.drop_column("ingestion_jobs", "index_manifest_generation")
    op.drop_column("ingestion_jobs", "index_previous_collection")
    op.drop_column("ingestion_jobs", "index_active_collection")
