"""add user tenant + sso fields

Revision ID: 007
Revises: 006
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            nullable=False,
            server_default="default",
        ),
    )
    op.add_column(
        "users",
        sa.Column("sso_provider", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("sso_subject_id", sa.String(length=255), nullable=True),
    )
    op.create_index("idx_users_tenant_id", "users", ["tenant_id"], if_not_exists=True)
    op.create_index(
        "uq_users_sso_provider_subject_id",
        "users",
        ["sso_provider", "sso_subject_id"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_sso_provider_subject_id", table_name="users")
    op.drop_index("idx_users_tenant_id", table_name="users")
    op.drop_column("users", "sso_subject_id")
    op.drop_column("users", "sso_provider")
    op.drop_column("users", "tenant_id")
