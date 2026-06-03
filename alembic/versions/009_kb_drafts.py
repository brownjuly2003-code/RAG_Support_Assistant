"""add kb drafts

Revision ID: 009
Revises: 008
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("draft_content", sa.Text(), nullable=False),
        sa.Column("source_ticket_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_kb_drafts_tenant_id", "kb_drafts", ["tenant_id"], if_not_exists=True)
    op.create_index("idx_kb_drafts_status", "kb_drafts", ["status"], if_not_exists=True)
    op.create_index("idx_kb_drafts_created_at", "kb_drafts", ["created_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_kb_drafts_created_at", table_name="kb_drafts")
    op.drop_index("idx_kb_drafts_status", table_name="kb_drafts")
    op.drop_index("idx_kb_drafts_tenant_id", table_name="kb_drafts")
    op.drop_table("kb_drafts")
