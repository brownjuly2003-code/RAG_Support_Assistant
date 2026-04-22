"""experiment deployment lifecycle

Revision ID: 015
Revises: 014
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_deployments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("experiment_id", sa.String(length=128), nullable=False),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("regression_run_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_experiment_deployments_experiment_id",
        "experiment_deployments",
        ["experiment_id"],
    )
    op.create_index(
        "ix_experiment_deployments_deployed_at",
        "experiment_deployments",
        ["deployed_at"],
    )
    op.create_index(
        "ix_experiment_deployments_rolled_back_at",
        "experiment_deployments",
        ["rolled_back_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experiment_deployments_rolled_back_at",
        table_name="experiment_deployments",
    )
    op.drop_index(
        "ix_experiment_deployments_deployed_at",
        table_name="experiment_deployments",
    )
    op.drop_index(
        "ix_experiment_deployments_experiment_id",
        table_name="experiment_deployments",
    )
    op.drop_table("experiment_deployments")
