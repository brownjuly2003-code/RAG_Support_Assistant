# agent/__init__.py
"""
Пакет agent:
- state.py — модель состояния для LangGraph pipeline.
- prompts.py — промпты для QA и self-evaluation.
- graph.py — сборка графа: retrieve → generate → evaluate → route → log.

Модули лежат в корне проекта; здесь re-export для удобства импорта.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so root-level modules are importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

# Re-export from root-level modules
from state import GraphState, create_initial_state  # noqa: E402, F401
from prompts import (  # noqa: E402, F401
    build_qa_prompt,
    build_self_eval_prompt,
    build_query_transform_prompt,
    build_doc_grade_prompt,
    build_query_rewrite_prompt,
    build_conversational_qa_prompt,
    build_conversational_query_transform_prompt,
    build_multi_query_prompt,
)
