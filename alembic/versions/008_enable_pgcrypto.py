"""enable pgcrypto and encrypt sensitive columns

Revision ID: 008
Revises: 007
"""
from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

_PGCRYPTO_OPTIONS = "cipher-algo=aes256,compress-algo=0"
_SENSITIVE_COLUMNS = (
    ("messages", "content"),
    ("audit_log", "detail"),
    ("escalated_tickets", "user_question"),
    ("escalated_tickets", "ai_draft"),
    ("escalated_tickets", "operator_response"),
)


def _require_key() -> str:
    key = os.getenv("DB_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("DB_ENCRYPTION_KEY is required for pgcrypto migration")
    return key


def _encrypt_column_sql(table_name: str, column_name: str) -> sa.TextClause:
    return sa.text(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE BYTEA
        USING CASE
            WHEN {column_name} IS NULL THEN NULL
            ELSE pgp_sym_encrypt({column_name}, :key, '{_PGCRYPTO_OPTIONS}')
        END
        """
    )


def _decrypt_column_sql(table_name: str, column_name: str) -> sa.TextClause:
    return sa.text(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE TEXT
        USING CASE
            WHEN {column_name} IS NULL THEN NULL
            ELSE pgp_sym_decrypt({column_name}, :key)
        END
        """
    )


def upgrade() -> None:
    connection = op.get_bind()
    key = _require_key()

    connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    for table_name, column_name in _SENSITIVE_COLUMNS:
        connection.execute(_encrypt_column_sql(table_name, column_name), {"key": key})


def downgrade() -> None:
    connection = op.get_bind()
    key = _require_key()

    for table_name, column_name in reversed(_SENSITIVE_COLUMNS):
        connection.execute(_decrypt_column_sql(table_name, column_name), {"key": key})
