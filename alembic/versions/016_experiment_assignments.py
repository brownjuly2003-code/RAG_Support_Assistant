"""tenant experiment assignments

Revision ID: 016
Revises: 015
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("experiment_id", sa.String(length=128), nullable=False),
        sa.Column(
            "rolled_out_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("rollout_percentage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_experiment_assignments_tenant_id",
        "experiment_assignments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_experiment_assignments_experiment_id",
        "experiment_assignments",
        ["experiment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experiment_assignments_experiment_id",
        table_name="experiment_assignments",
    )
    op.drop_index(
        "ix_experiment_assignments_tenant_id",
        table_name="experiment_assignments",
    )
    op.drop_table("experiment_assignments")
