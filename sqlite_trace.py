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
from datetime import datetime, timedelta, timezone
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
    return Path(__file__).resolve().parent


def _get_db_path() -> Path:
    """
    Строит путь к SQLite-базе для трейсинга и гарантирует, что
    директория существует.
    """
    try:
        from config.settings import get_settings

        db_path = Path(get_settings().tracing_db_path)
    except Exception:
        root = _get_project_root()
        db_path = root / "data" / "tracing" / "traces.db"

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


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

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id    TEXT,
                session_id  TEXT,
                rating      TEXT CHECK(rating IN ('up','down')),
                reason      TEXT,
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

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_traces_started_at
            ON traces(started_at);
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


def start_trace(trace_id: str | None = None) -> str:
    """
    Начинает новую трассу: создаёт запись в таблице traces и возвращает trace_id.

    :return: trace_id (строка UUID4), который нужно хранить в состоянии и
             использовать при логировании шагов.
    """
    if trace_id is None:
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


def save_feedback(
    trace_id: str,
    session_id: str,
    rating: str,
    reason: str = "",
) -> None:
    """Сохраняет пользовательский фидбек на ответ ассистента."""
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO feedback (trace_id, session_id, rating, reason, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, session_id, rating, reason, _now_iso()),
        )
        conn.commit()


def purge_old_traces(retention_days: int) -> dict[str, int]:
    """Удаляет traces старше retention_days и связанные steps/feedback."""
    if retention_days <= 0:
        return {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT trace_id FROM traces WHERE started_at < ?",
            (cutoff_iso,),
        )
        old_trace_ids = [row[0] for row in cur.fetchall()]

        if not old_trace_ids:
            return {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}

        def _batch(seq: list[str], size: int = 500):
            for index in range(0, len(seq), size):
                yield seq[index:index + size]

        steps_deleted = 0
        feedback_deleted = 0
        for batch in _batch(old_trace_ids):
            placeholders = ",".join("?" for _ in batch)
            cur.execute(
                f"DELETE FROM trace_steps WHERE trace_id IN ({placeholders})",
                batch,
            )
            steps_deleted += cur.rowcount
            cur.execute(
                f"DELETE FROM feedback WHERE trace_id IN ({placeholders})",
                batch,
            )
            feedback_deleted += cur.rowcount

        cur.execute("DELETE FROM traces WHERE started_at < ?", (cutoff_iso,))
        traces_deleted = cur.rowcount
        conn.commit()

    return {
        "traces_deleted": traces_deleted,
        "steps_deleted": steps_deleted,
        "feedback_deleted": feedback_deleted,
    }


def get_feedback_stats(days: int = 30) -> dict:
    """Aggregated feedback stats for the last N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    with _get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT rating, COUNT(*) FROM feedback WHERE ts >= ? GROUP BY rating",
            (cutoff,),
        )
        counts = dict(cur.fetchall())
        up = counts.get("up", 0)
        down = counts.get("down", 0)
        total = up + down
        up_pct = round(up / total * 100, 1) if total else 0.0

        cur.execute(
            """
            SELECT t.final_route, f.rating, COUNT(*)
            FROM feedback f
            LEFT JOIN traces t ON f.trace_id = t.trace_id
            WHERE f.ts >= ?
            GROUP BY t.final_route, f.rating
            """,
            (cutoff,),
        )
        by_route: Dict[str, Dict[str, int]] = {}
        for route, rating, count in cur.fetchall():
            route_key = route or "unknown"
            if route_key not in by_route:
                by_route[route_key] = {"up": 0, "down": 0}
            if rating in ("up", "down"):
                by_route[route_key][rating] += count

    return {
        "total": total,
        "up": up,
        "down": down,
        "up_pct": up_pct,
        "by_route": by_route,
        "period_days": days,
    }


def get_metrics_snapshot() -> dict:
    """Агрегированный снапшот метрик здоровья сервиса."""
    with _get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            WITH latencies AS (
                SELECT (julianday(finished_at) - julianday(started_at)) * 86400.0 AS s
                FROM traces
                WHERE finished_at IS NOT NULL
                  AND julianday(started_at) >= julianday('now', '-1 day')
            ),
            ranked AS (
                SELECT s, ROW_NUMBER() OVER (ORDER BY s) AS rn, COUNT(*) OVER () AS total
                FROM latencies
            )
            SELECT
                ROUND(MIN(CASE WHEN rn >= total * 0.50 THEN s END), 2) AS p50,
                ROUND(MIN(CASE WHEN rn >= total * 0.95 THEN s END), 2) AS p95,
                ROUND(MIN(CASE WHEN rn >= total * 0.99 THEN s END), 2) AS p99
            FROM ranked
            """
        )
        row = cur.fetchone()
        latency = {
            "p50_sec": row[0] if row and row[0] is not None else None,
            "p95_sec": row[1] if row and row[1] is not None else None,
            "p99_sec": row[2] if row and row[2] is not None else None,
            "window": "24h",
        }

        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN final_route = 'human' THEN 1 ELSE 0 END) AS escalated,
                ROUND(
                    100.0 * SUM(CASE WHEN final_route = 'human' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    1
                ) AS rate_pct
            FROM traces
            WHERE julianday(started_at) >= julianday('now', '-1 day')
            """
        )
        row = cur.fetchone()
        escalation = {
            "total_traces": row[0] if row and row[0] is not None else 0,
            "escalated": row[1] if row and row[1] is not None else 0,
            "rate_pct": row[2] if row and row[2] is not None else None,
            "window": "24h",
        }

        cur.execute(
            """
            SELECT
                COUNT(final_quality) AS scored,
                ROUND(AVG(final_quality), 1) AS avg_q,
                ROUND(
                    100.0 * SUM(CASE WHEN final_quality < 60 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(final_quality), 0),
                    1
                ) AS low_share
            FROM traces
            WHERE final_quality IS NOT NULL
              AND julianday(started_at) >= julianday('now', '-7 day')
            """
        )
        row = cur.fetchone()
        quality = {
            "scored_traces": row[0] if row and row[0] is not None else 0,
            "avg_quality": row[1] if row and row[1] is not None else None,
            "low_quality_share_pct": row[2] if row and row[2] is not None else None,
            "window": "7d",
        }

        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN finished_at IS NULL
                         AND julianday(started_at) < julianday('now', '-15 minute')
                        THEN 1 ELSE 0
                    END
                ) AS failed,
                ROUND(
                    100.0 * SUM(
                        CASE
                            WHEN finished_at IS NULL
                             AND julianday(started_at) < julianday('now', '-15 minute')
                            THEN 1 ELSE 0
                        END
                    ) / NULLIF(COUNT(*), 0),
                    1
                ) AS rate
            FROM traces
            WHERE julianday(started_at) >= julianday('now', '-1 day')
            """
        )
        row = cur.fetchone()
        errors = {
            "total_started": row[0] if row and row[0] is not None else 0,
            "likely_failed": row[1] if row and row[1] is not None else 0,
            "likely_failure_rate_pct": row[2] if row and row[2] is not None else None,
            "window": "24h",
        }

        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END) AS thumbs_down,
                ROUND(
                    100.0 * SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    1
                ) AS rate
            FROM feedback
            WHERE julianday(ts) >= julianday('now', '-7 day')
            """
        )
        row = cur.fetchone()
        feedback = {
            "total": row[0] if row and row[0] is not None else 0,
            "thumbs_down": row[1] if row and row[1] is not None else 0,
            "thumbs_down_rate_pct": row[2] if row and row[2] is not None else None,
            "window": "7d",
        }

    return {
        "latency": latency,
        "escalation": escalation,
        "quality": quality,
        "errors": errors,
        "feedback": feedback,
        "generated_at": _now_iso(),
    }
