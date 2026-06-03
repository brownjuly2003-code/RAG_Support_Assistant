"""add escalated tickets

Revision ID: 004
Revises: 003
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "escalated_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("user_question", sa.Text(), nullable=False),
        sa.Column("ai_draft", sa.Text(), nullable=True),
        sa.Column("operator_response", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_escalated_tickets_tenant_id", "escalated_tickets", ["tenant_id"], if_not_exists=True)
    op.create_index("idx_escalated_tickets_session_id", "escalated_tickets", ["session_id"], if_not_exists=True)
    op.create_index("idx_escalated_tickets_status", "escalated_tickets", ["status"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_escalated_tickets_status", table_name="escalated_tickets")
    op.drop_index("idx_escalated_tickets_session_id", table_name="escalated_tickets")
    op.drop_index("idx_escalated_tickets_tenant_id", table_name="escalated_tickets")
    op.drop_table("escalated_tickets")
