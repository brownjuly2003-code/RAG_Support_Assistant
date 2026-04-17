# Task 40 — SEC-5: Bare except cleanup в graph.py

## Goal
В `graph.py` есть `except Exception: pass` — молчаливое проглатывание ошибок.
Это делает отладку в production невозможной.
Заменить на specific exception handlers с логированием.

## Files to change
- `graph.py` — 2 bare except + pass (строки 75, 124)
- `api/app.py` — bare excepts в import-блоках (строки 71, 93, 144, 149)

---

## 1. graph.py — строка 75

Функция `_escalate_to_inbox`, import mock_inbox.

было:
```python
    try:
        from mock_inbox import get_support_sink  # type: ignore[import-not-found]
        get_support_sink().send(trace_id, _json.dumps(record, ensure_ascii=False))
        return
    except Exception:
        pass
```

стало:
```python
    try:
        from mock_inbox import get_support_sink  # type: ignore[import-not-found]
        get_support_sink().send(trace_id, _json.dumps(record, ensure_ascii=False))
        return
    except ImportError:
        logger.debug("mock_inbox not available, falling back to JSONL")
    except Exception as exc:
        logger.warning("Failed to send to support sink: %s", exc)
```

## 2. graph.py — строка 124

Функция `make_handle_error_node`, log_step.

было:
```python
        try:
            log_step(trace_id, "handle_error", state)
        except Exception:
            pass
```

стало:
```python
        try:
            log_step(trace_id, "handle_error", state)
        except Exception as exc:
            logger.warning("Failed to log handle_error step: %s", exc, extra={"trace_id": trace_id})
```

## 3. api/app.py — строка 71

было:
```python
try:
    from config.logging_config import setup_logging
    setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)
```

стало:
```python
try:
    from config.logging_config import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)
```

## 4. api/app.py — строка 93 (внутри _stream_ollama)

было:
```python
                try:
                    chunk = _json.loads(line)
                except Exception:
                    continue
```

стало:
```python
                try:
                    chunk = _json.loads(line)
                except (ValueError, _json.JSONDecodeError):
                    continue
```

## 5. api/app.py — строки 144, 149 (import fallback chain)

было:
```python
try:
    from graph import ConversationSession, run_qa_pipeline
    _ConversationSession = ConversationSession
    _run_qa_pipeline = run_qa_pipeline
except Exception:
    try:
        from agent.graph import ConversationSession, run_qa_pipeline
        _ConversationSession = ConversationSession
        _run_qa_pipeline = run_qa_pipeline
    except Exception:
        pass
```

стало:
```python
try:
    from graph import ConversationSession, run_qa_pipeline
    _ConversationSession = ConversationSession
    _run_qa_pipeline = run_qa_pipeline
except ImportError:
    try:
        from agent.graph import ConversationSession, run_qa_pipeline
        _ConversationSession = ConversationSession
        _run_qa_pipeline = run_qa_pipeline
    except ImportError:
        logger.info("RAG pipeline not available — graph module not found")
```

Аналогично для всех остальных import-fallback блоков в api/app.py (строки 157-188):
заменить `except ImportError` (уже корректные) оставить как есть,
а `except Exception` → `except ImportError`.

---

## CONSTRAINTS
- Изменить только `graph.py` и `api/app.py`
- Не менять логику — только exception types и добавить logging
- Import fallback chains: `Exception` → `ImportError`
- Runtime exceptions: `Exception: pass` → `Exception as exc: logger.warning(...)`
- `pytest tests/ -v` — проходит
- `grep -rn "except Exception:\s*$" graph.py api/app.py` → находит только те, что с `as exc` и handler

## DONE WHEN
- [ ] `grep "except Exception:" graph.py` — 0 bare catches (все с `as exc` + logging)
- [ ] Import fallbacks в api/app.py используют `ImportError`, не `Exception`
- [ ] `_json.loads` ловит `ValueError`/`JSONDecodeError`, не `Exception`
- [ ] `pytest tests/ -v` — проходит
