from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa


def test_encrypted_text_uses_pgcrypto_for_bind_and_select(monkeypatch) -> None:
    from db import crypto as crypto_module

    monkeypatch.setattr(
        crypto_module,
        "get_settings",
        lambda: SimpleNamespace(db_encryption_key="test-db-key"),
    )

    encrypted_type = crypto_module.EncryptedText()
    bind_sql = str(encrypted_type.bind_expression(sa.bindparam("content")))
    column_sql = str(encrypted_type.column_expression(sa.column("content")))

    assert "pgp_sym_encrypt" in bind_sql
    assert "pgp_sym_decrypt" in column_sql
    assert "cipher-algo=aes256" in bind_sql


def test_sensitive_models_use_encrypted_text() -> None:
    from db.crypto import EncryptedText
    from db.models import AuditLog, EscalatedTicket, Message

    assert isinstance(Message.__table__.c.content.type, EncryptedText)
    assert isinstance(AuditLog.__table__.c.detail.type, EncryptedText)
    assert isinstance(EscalatedTicket.__table__.c.user_question.type, EncryptedText)
    assert isinstance(EscalatedTicket.__table__.c.ai_draft.type, EncryptedText)
    assert isinstance(EscalatedTicket.__table__.c.operator_response.type, EncryptedText)


def test_pgcrypto_migration_encrypts_sensitive_columns(monkeypatch) -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "008_enable_pgcrypto.py"
    )
    spec = importlib.util.spec_from_file_location("migration_008_enable_pgcrypto", migration_path)
    assert spec is not None and spec.loader is not None
    migration_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_module)

    statements: list[tuple[str, dict | None]] = []

    class _FakeConnection:
        def execute(self, statement, params=None):
            statements.append((str(statement), params))

    monkeypatch.setenv("DB_ENCRYPTION_KEY", "super-secret-key")
    monkeypatch.setattr(migration_module.op, "get_bind", lambda: _FakeConnection())

    migration_module.upgrade()

    sql_blob = "\n".join(sql for sql, _params in statements)
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in sql_blob
    assert "ALTER TABLE messages" in sql_blob
    assert "ALTER TABLE audit_log" in sql_blob
    assert "ALTER TABLE escalated_tickets" in sql_blob
    assert "pgp_sym_encrypt" in sql_blob
    assert any(params == {"key": "super-secret-key"} for _sql, params in statements)
