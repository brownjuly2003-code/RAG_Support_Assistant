"""add document stats

Revision ID: 010
Revises: 009
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("doc_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_cited_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("doc_id", "tenant_id", name="uq_document_stats_doc_tenant"),
    )
    op.create_index("idx_document_stats_tenant_id", "document_stats", ["tenant_id"], if_not_exists=True)
    op.create_index("idx_document_stats_doc_id", "document_stats", ["doc_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_document_stats_doc_id", table_name="document_stats")
    op.drop_index("idx_document_stats_tenant_id", table_name="document_stats")
    op.drop_table("document_stats")
