"""add review queue

Revision ID: 012
Revises: 011
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None
_REVIEW_QUEUE_REASON_VALUES = (
    "thumbs_down",
    "low_quality",
    "escalated",
    "fact_fail",
    "slow_trace",
    "manual",
)
_REVIEW_QUEUE_STATUS_VALUES = (
    "pending",
    "in_review",
    "confirmed_good",
    "confirmed_bad",
    "dismissed",
)


def upgrade() -> None:
    bind = op.get_bind()
    reason_enum = postgresql.ENUM(
        *_REVIEW_QUEUE_REASON_VALUES,
        name="review_queue_reason",
    )
    status_enum = postgresql.ENUM(
        *_REVIEW_QUEUE_STATUS_VALUES,
        name="review_queue_status",
    )
    reason_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)

    op.create_table(
        "review_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "trace_id",
            sa.String(length=64),
            sa.ForeignKey("traces.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(*_REVIEW_QUEUE_REASON_VALUES, name="review_queue_reason"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(*_REVIEW_QUEUE_STATUS_VALUES, name="review_queue_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_review_queue_tenant_status_created_at",
        "review_queue",
        ["tenant_id", "status", "created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    reason_enum = postgresql.ENUM(
        *_REVIEW_QUEUE_REASON_VALUES,
        name="review_queue_reason",
    )
    status_enum = postgresql.ENUM(
        *_REVIEW_QUEUE_STATUS_VALUES,
        name="review_queue_status",
    )

    op.drop_index("ix_review_queue_tenant_status_created_at", table_name="review_queue")
    op.drop_table("review_queue")
    status_enum.drop(bind, checkfirst=True)
    reason_enum.drop(bind, checkfirst=True)
