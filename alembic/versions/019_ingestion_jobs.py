"""durable tenant-aware ingestion jobs

Revision ID: 019
Revises: 018
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_tenant_id_created_at",
        "ingestion_jobs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_ingestion_jobs_status",
        "ingestion_jobs",
        ["status"],
    )
    op.create_index(
        "ix_ingestion_jobs_celery_task_id",
        "ingestion_jobs",
        ["celery_task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_celery_task_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_tenant_id_created_at", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
