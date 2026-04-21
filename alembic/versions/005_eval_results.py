"""add eval results

Revision ID: 005
Revises: 004
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("metric_name", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("drift_alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("idx_eval_results_created_at", "eval_results", ["created_at"], if_not_exists=True)
    op.create_index("idx_eval_results_metric_name", "eval_results", ["metric_name"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_eval_results_metric_name", table_name="eval_results")
    op.drop_index("idx_eval_results_created_at", table_name="eval_results")
    op.drop_table("eval_results")
