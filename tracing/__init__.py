# tracing/__init__.py
"""
Пакет локального мини-LangSmith:
- sqlite_trace.py — трейсинг шагов графа в SQLite.

Re-export из корневого sqlite_trace.py.
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from sqlite_trace import start_trace, log_step, finish_trace  # noqa: E402, F401
