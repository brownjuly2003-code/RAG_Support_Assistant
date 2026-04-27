# tracing/__init__.py
"""
Пакет локального мини-LangSmith:
- _base_trace.py — базовый SQLite trace store.
- sqlite_trace.py — PII-safe wrapper для шагов графа.
"""

from tracing.sqlite_trace import finish_trace, log_step, start_trace  # noqa: F401
