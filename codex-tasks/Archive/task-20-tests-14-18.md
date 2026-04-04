# Task 20 — Tests for task-14..18

## Goal
Покрыть тестами все новые endpoints и флаги из task-14..18.
Сейчас 19 тестов, ни одного для feedback, SSE, sessions list, HyDE, parent-child.

## File to change
- `tests/test_new_features.py` — новый файл

## Test cases

Создать `tests/test_new_features.py`. Использовать тот же паттерн что в других тестах
(смотри `tests/test_health.py` — там есть `_install_slowapi_stub()` и TestClient setup).

### 1. POST /api/feedback — happy path
```python
def test_feedback_up(client):
    resp = client.post("/api/feedback", json={
        "trace_id": "test-trace-001",
        "session_id": "test-session-001",
        "rating": "up",
    })
    assert resp.status_code == 204
```

### 2. POST /api/feedback — invalid rating
```python
def test_feedback_invalid_rating(client):
    resp = client.post("/api/feedback", json={
        "trace_id": "test-trace-001",
        "session_id": "test-session-001",
        "rating": "meh",
    })
    assert resp.status_code == 422
```

### 3. POST /api/feedback — down rating
```python
def test_feedback_down(client):
    resp = client.post("/api/feedback", json={
        "trace_id": "t2", "session_id": "s2", "rating": "down", "reason": "wrong answer"
    })
    assert resp.status_code == 204
```

### 4. GET /api/sessions — empty and with session
```python
def test_sessions_list_empty(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_sessions_list_after_ask(client, monkeypatch):
    # Вызвать /api/ask → создастся сессия → GET /api/sessions должен её вернуть
    # Замокать session.ask чтобы не нужен Ollama
    # (используй тот же mock-паттерн из test_health.py или test_rate_limiting.py)
    pass  # реализовать по паттерну файла
```

### 5. POST /api/ask/stream — возвращает text/event-stream
```python
def test_ask_stream_content_type(client, monkeypatch):
    # Замокать pipeline чтобы вернул фиктивный ответ
    resp = client.post("/api/ask/stream",
        json={"question": "тест", "session_id": None},
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
```

### 6. GraphState содержит hyde_query
```python
from state import create_initial_state

def test_state_has_hyde_query():
    state = create_initial_state("question")
    assert "hyde_query" in state
    assert state["hyde_query"] is None
```

### 7. HyDE disabled by default
```python
from config.settings import get_settings

def test_hyde_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RAG_HYDE", raising=False)
    # Пересоздать Settings напрямую (не через get_settings() singleton)
    from config.settings import Settings
    s = Settings()
    assert s.hyde is False
```

### 8. Parent-child disabled by default
```python
def test_parent_child_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RAG_PARENT_CHILD", raising=False)
    from config.settings import Settings
    s = Settings()
    assert s.parent_child is False
```

### 9. build_retriever возвращает HybridRetriever при parent_child=False
```python
def test_build_retriever_default():
    from manager import build_retriever, HybridRetriever
    from unittest.mock import MagicMock, patch
    with patch("manager.get_settings") as mock_settings:
        mock_settings.return_value.parent_child = False
        mock_settings.return_value.hybrid_search = False
        mock_settings.return_value.retrieval_top_k = 5
        mock_settings.return_value.rerank_top_k = 3
        mock_settings.return_value.reranker_model = ""
        retriever = build_retriever(docs=[], embeddings=MagicMock())
    assert isinstance(retriever, HybridRetriever)
```

## CONSTRAINTS
- Создать только `tests/test_new_features.py`
- Использовать тот же `client` fixture что в других test-файлах (или создать локально)
- Тесты НЕ должны требовать запущенного Ollama или ChromaDB
- Все mock-и делать через `monkeypatch` или `unittest.mock`
- `pytest tests/ -v` — все тесты проходят, count >= 27

## DONE WHEN
- [ ] `tests/test_new_features.py` создан
- [ ] Минимум 9 тестов в файле
- [ ] Тест на 422 для неверного rating
- [ ] Тест на hyde_query в GraphState
- [ ] Тест на hyde=False и parent_child=False по умолчанию
- [ ] `pytest tests/ -v` — все проходят
