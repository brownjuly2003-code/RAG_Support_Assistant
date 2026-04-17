# Task 44 — DB-3: Alembic миграции

## Goal
Настроить Alembic для версионирования схемы PostgreSQL.
Создать начальную миграцию с таблицами из `db/models.py`.

## Dependencies
- task-43 (SQLAlchemy модели)

## Files to create
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/001_initial_schema.py`

## Files to change
- `requirements.txt` — добавить alembic

---

## 1. requirements.txt

Добавить:
```
alembic>=1.13.0
```

---

## 2. Инициализация

Выполнить:
```bash
cd /d/RAG_Support_Assistant
alembic init alembic
```

---

## 3. alembic.ini

Заменить строку `sqlalchemy.url`:

было:
```
sqlalchemy.url = driver://user:pass@localhost/dbname
```

стало:
```
sqlalchemy.url = postgresql://rag:rag_dev_password@localhost:5432/rag_assistant
```

---

## 4. alembic/env.py

В `env.py` подключить модели для autogenerate:

Добавить в начало (после существующих импортов):
```python
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import Base
```

Заменить `target_metadata`:

было:
```python
target_metadata = None
```

стало:
```python
target_metadata = Base.metadata
```

В функции `run_migrations_online()` добавить поддержку `DATABASE_URL` из env:

```python
import os

def run_migrations_online():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )
    ...
```

---

## 5. Начальная миграция

Сгенерировать:
```bash
alembic revision --autogenerate -m "initial schema: sessions, messages, traces, trace_steps, feedback"
```

Или создать вручную `alembic/versions/001_initial_schema.py`:

```python
"""initial schema: sessions, messages, traces, trace_steps, feedback

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_access', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'messages',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'traces',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('final_route', sa.String(30), nullable=True),
        sa.Column('final_quality', sa.Float, nullable=True),
        sa.Column('final_relevance', sa.Float, nullable=True),
    )

    op.create_table(
        'trace_steps',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('trace_id', sa.String(64), sa.ForeignKey('traces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_order', sa.Integer, nullable=False),
        sa.Column('node_name', sa.String(50), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state_json', sa.Text, nullable=True),
    )

    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('trace_id', sa.String(64), sa.ForeignKey('traces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('rating', sa.String(10), nullable=False),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('feedback')
    op.drop_table('trace_steps')
    op.drop_table('traces')
    op.drop_table('messages')
    op.drop_table('sessions')
```

---

## CONSTRAINTS
- Alembic config и миграции только
- При наличии PostgreSQL: `alembic upgrade head` создаёт все 5 таблиц
- `alembic downgrade base` удаляет все таблицы
- `pytest tests/ -v` — проходит (миграции не ломают существующий код)

## DONE WHEN
- [ ] `alembic.ini` настроен на PostgreSQL
- [ ] `alembic/env.py` подключает `Base.metadata` из `db/models.py`
- [ ] Начальная миграция создаёт 5 таблиц: sessions, messages, traces, trace_steps, feedback
- [ ] `alembic upgrade head` из чистой БД — успех
- [ ] `alembic downgrade base` — успех
- [ ] `pytest tests/ -v` — проходит
