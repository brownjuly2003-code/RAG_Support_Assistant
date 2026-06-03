"""add tenant_id columns

Revision ID: 003
Revises: 002
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

TENANT_TABLES = ("audit_log", "sessions")


def upgrade() -> None:
    for table_name in TENANT_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                nullable=False,
                server_default="default",
            ),
        )
        op.create_index(
            f"idx_{table_name}_tenant_id",
            table_name,
            ["tenant_id"],
            if_not_exists=True,
        )


def downgrade() -> None:
    for table_name in TENANT_TABLES:
        op.drop_index(f"idx_{table_name}_tenant_id", table_name=table_name)
        op.drop_column(table_name, "tenant_id")
