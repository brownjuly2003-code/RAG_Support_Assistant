"""add trace evaluations

Revision ID: 014
Revises: 013
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trace_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "trace_id",
            sa.String(length=64),
            sa.ForeignKey("traces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evaluator_name", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_trace_evaluations_trace_id", "trace_evaluations", ["trace_id"])
    op.create_index(
        "ix_trace_evaluations_evaluator_name_evaluated_at",
        "trace_evaluations",
        ["evaluator_name", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_evaluations_evaluator_name_evaluated_at", table_name="trace_evaluations")
    op.drop_index("ix_trace_evaluations_trace_id", table_name="trace_evaluations")
    op.drop_table("trace_evaluations")
