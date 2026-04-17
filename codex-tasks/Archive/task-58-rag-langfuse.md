# Task 58 — RQ-1: Langfuse integration для трейсинга LLM

## Goal
Добавить Langfuse для трейсинга каждого LLM-вызова: latency, tokens, cost.
Langfuse — open-source LLM observability, self-hosted или cloud.

## Files to create
- `tracing/langfuse_trace.py` — обёртка над Langfuse SDK

## Files to change
- `requirements.txt` — добавить langfuse
- `config/settings.py` — langfuse env vars
- `graph.py` — обернуть LLM.invoke в Langfuse spans

---

## 1. requirements.txt

Добавить:
```
langfuse>=2.0.0
```

---

## 2. config/settings.py

Добавить поля:
```python
    # Langfuse — LLM observability (optional)
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
```

---

## 3. tracing/langfuse_trace.py

```python
"""Langfuse LLM tracing integration."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_langfuse = None


def get_langfuse():
    """Lazy init Langfuse client. Returns None if not configured."""
    global _langfuse
    if _langfuse is not None:
        return _langfuse
    try:
        from config.settings import get_settings
        settings = get_settings()
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return None
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse connected: %s", settings.langfuse_host)
        return _langfuse
    except ImportError:
        logger.debug("langfuse package not installed")
        return None
    except Exception as exc:
        logger.warning("Langfuse init failed: %s", exc)
        return None


def trace_llm_call(
    trace_id: str,
    node_name: str,
    prompt: str,
    response: str,
    model: str = "",
    duration_ms: float = 0,
) -> None:
    """Log an LLM call to Langfuse."""
    lf = get_langfuse()
    if lf is None:
        return
    try:
        trace = lf.trace(id=trace_id, name="rag-pipeline")
        trace.generation(
            name=node_name,
            model=model,
            input=prompt[:5000],   # truncate for safety
            output=response[:5000],
            metadata={"duration_ms": duration_ms},
        )
    except Exception as exc:
        logger.warning("Langfuse trace failed: %s", exc)


def flush() -> None:
    """Flush Langfuse queue."""
    lf = get_langfuse()
    if lf is not None:
        try:
            lf.flush()
        except Exception:
            pass
```

---

## 4. graph.py — интеграция

В node-функциях generate и evaluate, после LLM invoke:

```python
import time

t0 = time.monotonic()
raw = llm.invoke(prompt)
duration_ms = (time.monotonic() - t0) * 1000

try:
    from tracing.langfuse_trace import trace_llm_call
    trace_llm_call(
        trace_id=state.get("trace_id", ""),
        node_name="generate",  # или "evaluate", "transform_query"
        prompt=prompt[:2000],
        response=raw[:2000],
        model=getattr(llm, '_llm', {}).model if hasattr(llm, '_llm') else "",
        duration_ms=duration_ms,
    )
except ImportError:
    pass
```

---

## 5. .env.example

Добавить:
```
# Langfuse — LLM observability (optional, leave empty to disable)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## CONSTRAINTS
- Langfuse optional: без ключей — ничего не происходит
- Не замедлять pipeline: trace_llm_call не блокирует
- `pytest tests/ -v` — проходит (без Langfuse ключей)

## DONE WHEN
- [ ] `tracing/langfuse_trace.py` создан
- [ ] Langfuse env vars в settings.py и .env.example
- [ ] С Langfuse ключами: каждый LLM-call логируется
- [ ] Без ключей: никакого эффекта, нет ошибок
- [ ] `pytest tests/ -v` — проходит
