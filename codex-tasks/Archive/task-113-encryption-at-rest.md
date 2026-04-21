# Task 113 — Encryption at rest: pgcrypto для sensitive fields

## Context
COMP-4 из commercial-plan. Сейчас PostgreSQL хранит все данные в plaintext.
Для SOC2/GDPR compliance нужно encryption at rest для sensitive полей:
user questions, answers, PII в audit logs. Полный disk-level encryption
— ответственность cloud provider'а; app-level column encryption —
наша.

Текущее состояние: PII redaction уже есть в logs/traces (COMP-2 done),
но сами колонки в sessions/messages/traces — plaintext.

## Goal
App-level encryption для:
- `messages.content` (user questions + bot answers)
- `audit_log.detail` (может содержать sensitive метаданные)
- `escalated_tickets.user_question`, `.ai_draft`, `.operator_response`

Использовать **pgcrypto** (PostgreSQL extension) с AES-256 и ключом,
хранящимся вне БД (env var KMS-style).

## Files to change
- `alembic/versions/008_enable_pgcrypto.py` — `CREATE EXTENSION IF NOT EXISTS pgcrypto`
- `db/crypto.py` — helper functions `encrypt(plaintext)` / `decrypt(ciphertext)`
  используя `pgcrypto.pgp_sym_encrypt` / `pgp_sym_decrypt` через SQL
- `db/models.py` — для sensitive полей использовать `EncryptedString`
  custom type (SQLAlchemy TypeDecorator) который автоматически
  шифрует/расшифровывает
- `config/settings.py` — `db_encryption_key: SecretStr` (обязательно для prod)
- `scripts/rotate_encryption_key.py` — опциональный script для rotation
- `tests/test_encryption.py` — round-trip test, migration test

## Implementation sketch

### Custom SQLAlchemy type (db/crypto.py)
```python
from sqlalchemy.types import TypeDecorator, String, Text
from sqlalchemy import func, text
from config import settings

class EncryptedText(TypeDecorator):
    """Column that transparently encrypts/decrypts using pgcrypto."""
    impl = Text
    cache_ok = True

    def bind_expression(self, bindvalue):
        key = settings.db_encryption_key.get_secret_value()
        return func.pgp_sym_encrypt(bindvalue, key)

    def column_expression(self, col):
        key = settings.db_encryption_key.get_secret_value()
        return func.pgp_sym_decrypt(col, key)
```

### Model changes (db/models.py)
```python
from db.crypto import EncryptedText

class Message(Base):
    # ...
    content: Mapped[str] = mapped_column(EncryptedText, nullable=False)

class AuditLog(Base):
    # ...
    detail: Mapped[str | None] = mapped_column(EncryptedText)

class EscalatedTicket(Base):
    user_question: Mapped[str] = mapped_column(EncryptedText)
    ai_draft: Mapped[str | None] = mapped_column(EncryptedText)
    operator_response: Mapped[str | None] = mapped_column(EncryptedText)
```

### Migration strategy
008 не только enable'ит pgcrypto, но и переконвертирует existing
plaintext rows:
```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    # Alter columns to bytea, migrate data:
    # Requires downtime OR double-write pattern. Для single-user local —
    # acceptable. Для prod — отдельный migration-план.
    key = os.environ["DB_ENCRYPTION_KEY"]
    op.execute(f"""
        ALTER TABLE messages
        ALTER COLUMN content TYPE bytea
        USING pgp_sym_encrypt(content, '{key}')
    """)
```
**Важно**: миграция требует доступ к key — он передаётся через env var
в момент миграции. Логирование миграции НЕ должно показывать key.

## CONSTRAINTS
- `db_encryption_key` — **required** в production; dev mode может
  default'ить на фиксированное известное значение (warning в logs)
- Key rotation — отдельный task (rotate_encryption_key.py script stub
  оставить, полная rotation-логика вне этой задачи)
- Performance: pgcrypto symmetric encryption ~10-50µs per op — приемлемо
  для OLTP
- Search по зашифрованным полям — невозможен. Если нужно search по
  `messages.content` (history search) — это **out of scope**. Пока
  history-search не используется, encryption безопасно
- Backup: бэкапы БД теперь encrypted; key должен бэкапиться отдельно
  (иначе бэкапы бесполезны)

## DONE WHEN
- [ ] pgcrypto extension enabled в миграции 008
- [ ] Sensitive поля encrypted через `EncryptedText` type
- [ ] Round-trip test: INSERT plaintext → SELECT → decrypted plaintext совпадает
- [ ] Direct SQL `SELECT content FROM messages LIMIT 1` показывает `bytea`
      (ciphertext), не plaintext
- [ ] Existing тесты проходят (transparent для app code)
- [ ] Задокументировано в README: `DB_ENCRYPTION_KEY` required + backup policy
- [ ] 255+ passed
- [ ] Commit: "Encryption at rest: pgcrypto for sensitive fields (task-113)"
