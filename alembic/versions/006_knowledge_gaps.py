"""add knowledge gaps

Revision ID: 006
Revises: 005
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("topic_summary", sa.Text(), nullable=False),
        sa.Column("sample_questions", sa.JSON(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_knowledge_gaps_tenant_id", "knowledge_gaps", ["tenant_id"], if_not_exists=True)
    op.create_index("idx_knowledge_gaps_cluster_id", "knowledge_gaps", ["cluster_id"], if_not_exists=True)
    op.create_index("idx_knowledge_gaps_created_at", "knowledge_gaps", ["created_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_knowledge_gaps_created_at", table_name="knowledge_gaps")
    op.drop_index("idx_knowledge_gaps_cluster_id", table_name="knowledge_gaps")
    op.drop_index("idx_knowledge_gaps_tenant_id", table_name="knowledge_gaps")
    op.drop_table("knowledge_gaps")
