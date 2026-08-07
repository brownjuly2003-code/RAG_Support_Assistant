"""escalated ticket idempotency and delivery state

Revision ID: 023
Revises: 022
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escalated_tickets",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "escalated_tickets",
        sa.Column("source", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "escalated_tickets",
        sa.Column("trace_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "escalated_tickets",
        sa.Column(
            "delivery_state",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "escalated_tickets",
        sa.Column("delivery_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_escalated_tickets_idempotency_key",
        "escalated_tickets",
        ["idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_escalated_tickets_idempotency_key",
        "escalated_tickets",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_escalated_tickets_idempotency_key",
        "escalated_tickets",
        type_="unique",
    )
    op.drop_index("ix_escalated_tickets_idempotency_key", table_name="escalated_tickets")
    op.drop_column("escalated_tickets", "delivery_error")
    op.drop_column("escalated_tickets", "delivery_state")
    op.drop_column("escalated_tickets", "trace_id")
    op.drop_column("escalated_tickets", "source")
    op.drop_column("escalated_tickets", "idempotency_key")
