"""add trace cost fields

Revision ID: 011
Revises: 010
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trace_steps", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("trace_steps", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("trace_steps", sa.Column("model_name", sa.String(length=100), nullable=True))
    op.add_column("trace_steps", sa.Column("cost_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trace_steps", "cost_usd")
    op.drop_column("trace_steps", "model_name")
    op.drop_column("trace_steps", "completion_tokens")
    op.drop_column("trace_steps", "prompt_tokens")
