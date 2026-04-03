"""
tracing/sqlite_trace.py

Локальный мини-аналог LangSmith на базе SQLite.

Задача этого модуля — сохранять "трассы" (прогоны) графа LangGraph в
простую SQLite-базу, чтобы потом можно было:

- смотреть список запросов (traces);
- открывать конкретную трассу и смотреть, какие узлы и в каком порядке
  выполнялись, как менялось состояние (trace_steps);
- на основе этих данных построить простую веб-панель.

Схема БД:

1) Таблица traces — один ряд = один проход графа (один trace_id)

   traces(
       trace_id        TEXT PRIMARY KEY,  -- идентификатор трассы (UUID)
       started_at      TEXT,              -- время начала (ISO 8601)
       finished_at     TEXT,              -- время завершения (ISO 8601) или NULL
       final_route     TEXT,              -- "auto" / "human" / NULL
       final_quality   INTEGER,           -- итоговый quality_score или NULL
       final_relevance REAL               -- итоговый relevance_score или NULL
   )

2) Таблица trace_steps — шаги внутри одной трассы

   trace_steps(
       id          INTEGER PRIMARY KEY AUTOINCREMENT,
       trace_id    TEXT,        -- внешний ключ на traces.trace_id
       step_order  INTEGER,     -- порядковый номер шага (0,1,2,...)
       node_name   TEXT,        -- имя узла графа ("retrieve", "generate", ...)
       state_json  TEXT,        -- JSON-снимок состояния после шага
       ts          TEXT         -- время записи шага (ISO 8601)
   )

Функции публичного интерфейса:

- start_trace() -> str
    Создаёт запись в traces, возвращает trace_id (строка UUID).

- log_step(trace_id: str, node_name: str, state: dict) -> None
    Добавляет запись в trace_steps с порядковым номером, именем узла,
    JSON состояния и временной меткой.

- finish_trace(trace_id: str, final_state: dict) -> None
    Обновляет запись в traces: проставляет finished_at и агрегированные
    поля (final_route, final_quality, final_relevance) из финального
    состояния графа.

Как построить простую веб-панель поверх этих данных:

1) Любой лёгкий веб-фреймворк (Flask / FastAPI / Streamlit):
   - Эндпоинт /traces:
       SELECT * FROM traces ORDER BY started_at DESC
     → отображаем таблицу: trace_id, started_at, final_route, final_quality.

   - Эндпоинт /traces/{trace_id}:
       SELECT * FROM trace_steps WHERE trace_id=? ORDER BY step_order
     → показываем шаги, node_name, ts и state_json; JSON можно
       подсветить при помощи JavaScript (например, json-viewer).

2) Можно добавить фильтры по final_route ("auto"/"human") и границам
   final_quality, чтобы быстро находить проблемные / спорные ответы.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _get_project_root() -> Path:
    """
    Определяет корень проекта относительно текущего файла.

    Предполагаем структуру вида:

        project_root/
            agent/
            tracing/
                sqlite_trace.py  ← мы здесь
            data/
                tracing/
                    traces.db
    """
    return Path(__file__).resolve().parent.parent


def _get_db_path() -> Path:
    """
    Строит путь к SQLite-базе для трейсинга и гарантирует, что
    директория существует.
    """
    root = _get_project_root()
    db_dir = root / "data" / "tracing"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "traces.db"


@contextmanager
def _get_connection():
    """Контекстный менеджер для подключения к SQLite.

    Каждый вызов открывает новое соединение и гарантированно его закрывает.
    Для PoC-уровня это абсолютно нормально.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _init_db() -> None:
    """Создаёт таблицы traces и trace_steps, если их ещё нет."""
    with _get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS traces (
                trace_id        TEXT PRIMARY KEY,
                started_at      TEXT,
                finished_at     TEXT,
                final_route     TEXT,
                final_quality   INTEGER,
                final_relevance REAL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id    TEXT,
                step_order  INTEGER,
                node_name   TEXT,
                state_json  TEXT,
                ts          TEXT
            );
            """
        )

        # Индекс по trace_id и step_order для ускорения выборок шагов
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trace_steps_trace
            ON trace_steps(trace_id, step_order);
            """
        )

        conn.commit()


# Инициализируем БД один раз при импорте модуля
_init_db()


def _now_iso() -> str:
    """Возвращает текущее время в UTC в формате ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _state_to_dict(state: Any) -> Dict[str, Any]:
    """
    Приводит состояние к обычному словарю для JSON-сериализации.

    - Если state уже dict → возвращаем копию.
    - Если у объекта есть метод dict() или model_dump() (Pydantic) → используем его.
    - В остальных случаях оборачиваем в {"value": repr(state)}.

    Это делает модуль устойчивым к небольшим изменениям представления
    состояния (TypedDict, Pydantic-модели и т.п.).
    """
    if isinstance(state, dict):
        return dict(state)

    # Pydantic v1: .dict(), v2: .model_dump()
    if hasattr(state, "model_dump") and callable(state.model_dump):  # type: ignore[attr-defined]
        return state.model_dump()  # type: ignore[no-any-return]
    if hasattr(state, "dict") and callable(state.dict):  # type: ignore[attr-defined]
        return state.dict()  # type: ignore[no-any-return]

    return {"value": repr(state)}


def start_trace() -> str:
    """
    Начинает новую трассу: создаёт запись в таблице traces и возвращает trace_id.

    :return: trace_id (строка UUID4), который нужно хранить в состоянии и
             использовать при логировании шагов.
    """
    trace_id = str(uuid.uuid4())
    started_at = _now_iso()

    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO traces (trace_id, started_at, finished_at, final_route, final_quality, final_relevance)
            VALUES (?, ?, NULL, NULL, NULL, NULL)
            """,
            (trace_id, started_at),
        )
        conn.commit()

    return trace_id


def log_step(trace_id: str, node_name: str, state: Any) -> None:
    """
    Логирует один шаг выполнения графа в таблицу trace_steps.

    Логика:
    1) Преобразуем state в словарь и сериализуем в JSON.
    2) Определяем следующий step_order как (MAX(step_order)+1) для данного trace_id.
    3) Записываем строку с именем узла и текущей временной меткой.
    """
    state_dict = _state_to_dict(state)
    state_json = json.dumps(state_dict, ensure_ascii=False)
    ts = _now_iso()

    with _get_connection() as conn:
        cur = conn.cursor()

        # Получаем текущий максимум step_order для этой трассы
        cur.execute(
            "SELECT COALESCE(MAX(step_order), -1) FROM trace_steps WHERE trace_id = ?",
            (trace_id,),
        )
        row = cur.fetchone()
        last_order = row[0] if row is not None else -1
        step_order = last_order + 1

        cur.execute(
            """
            INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, step_order, node_name, state_json, ts),
        )
        conn.commit()


def finish_trace(trace_id: str, final_state: Any) -> None:
    """
    Завершает трассу и обновляет агрегированные поля в таблице traces.

    Из финального состояния читаем:
    - route           → final_route
    - quality_score   → final_quality
    - relevance_score → final_relevance

    Если каких-то полей нет, просто сохраняем NULL.
    """
    finished_at = _now_iso()
    state_dict = _state_to_dict(final_state)

    final_route = state_dict.get("route")
    final_quality = state_dict.get("quality_score")
    final_relevance = state_dict.get("relevance_score")

    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE traces
            SET finished_at = ?,
                final_route = ?,
                final_quality = ?,
                final_relevance = ?
            WHERE trace_id = ?
            """,
            (finished_at, final_route, final_quality, final_relevance, trace_id),
        )
        conn.commit()
