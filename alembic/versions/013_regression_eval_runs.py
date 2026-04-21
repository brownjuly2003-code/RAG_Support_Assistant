"""extend eval results for regression runs

Revision ID: 013
Revises: 012
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "eval_results",
        sa.Column("kind", sa.String(length=30), nullable=False, server_default="nightly"),
    )
    op.add_column(
        "eval_results",
        sa.Column("run_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "eval_results",
        sa.Column("baseline_experiment_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "eval_results",
        sa.Column("candidate_experiment_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "eval_results",
        sa.Column("report_path", sa.String(length=255), nullable=True),
    )
    op.create_index("idx_eval_results_kind", "eval_results", ["kind"], if_not_exists=True)
    op.create_index("uq_eval_results_run_id", "eval_results", ["run_id"], unique=True, if_not_exists=True)


def downgrade() -> None:
    op.drop_index("uq_eval_results_run_id", table_name="eval_results")
    op.drop_index("idx_eval_results_kind", table_name="eval_results")
    op.drop_column("eval_results", "report_path")
    op.drop_column("eval_results", "candidate_experiment_id")
    op.drop_column("eval_results", "baseline_experiment_id")
    op.drop_column("eval_results", "run_id")
    op.drop_column("eval_results", "kind")
