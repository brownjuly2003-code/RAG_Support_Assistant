"""message tenant ownership composite FK

Revision ID: 018
Revises: 017
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add nullable ownership column first so existing rows can be backfilled.
    op.add_column(
        "messages",
        sa.Column("tenant_id", sa.String(length=50), nullable=True),
    )

    # 2) Deterministic backfill from the owning session (no silent default).
    op.execute(
        sa.text(
            """
            UPDATE messages
            SET tenant_id = sessions.tenant_id
            FROM sessions
            WHERE messages.session_id = sessions.id
            """
        )
    )

    # 3) Refuse to proceed if any Message remains unowned.
    bind = op.get_bind()
    unowned = bind.execute(
        sa.text("SELECT COUNT(*) FROM messages WHERE tenant_id IS NULL")
    ).scalar()
    if unowned:
        raise RuntimeError(
            f"Cannot enforce Message.tenant_id NOT NULL: {unowned} unowned row(s) "
            "remain after backfill from sessions"
        )

    # 4) Require tenant ownership on every Message row.
    op.alter_column(
        "messages",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    # 5) Session composite unique key required by the ownership FK.
    op.create_unique_constraint(
        "uq_sessions_id_tenant_id",
        "sessions",
        ["id", "tenant_id"],
    )

    # 6) Replace the independent single-column FK after backfill.
    op.drop_constraint("messages_session_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "fk_messages_session_tenant",
        "messages",
        "sessions",
        ["session_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )

    # 7) Tenant lookup index on messages.
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])


def downgrade() -> None:
    # Drop composite ownership artifacts in dependency-safe order.
    op.drop_constraint("fk_messages_session_tenant", "messages", type_="foreignkey")
    op.drop_index("ix_messages_tenant_id", table_name="messages")
    op.drop_constraint("uq_sessions_id_tenant_id", "sessions", type_="unique")

    # Restore the original single-column session FK before removing tenant_id.
    op.create_foreign_key(
        "messages_session_id_fkey",
        "messages",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("messages", "tenant_id")
