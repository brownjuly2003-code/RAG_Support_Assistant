# Task 122 — Integration tests: end-to-end flow (PROD-4)

## Context
PROD-4 из rec.md. 222 passing теста — это **unit** tests (nodes, auth,
rate-limits etc.). Нет полного end-to-end: upload → ingest → index →
retrieve → answer. Unit-тесты могут проходить при сломанном integration'е
(mock'и врут).

Commercial-grade: integration suite, запускается на CI, покрывает
critical user paths.

## Goal
Добавить `tests/integration/` со сьютом который покрывает:
1. **Full ingestion → retrieval** — upload PDF → чанки → embeddings →
   retrieve returns relevant chunk
2. **Multi-turn conversation** — 3 сообщения, каждое видит предыдущий
   context
3. **SSE streaming** — `/api/ask/stream` endpoint возвращает chunks
4. **Concurrent sessions** — 5 sessions параллельно, tenant isolation
5. **Escalation flow** — low-quality → escalation_sink → ticket в DB
6. **Upload async task** — Celery task processes upload, polling returns
   completed

## Files to change
- `tests/integration/__init__.py`
- `tests/integration/conftest.py` — fixtures для integration:
  - Real ChromaDB (in-memory или tmpfs)
  - Real Redis (testcontainers или in-memory fakeredis)
  - Real Postgres (testcontainers или sqlite-in-memory с SQLAlchemy)
  - Real Ollama — опционально; fallback на LLM stub
- `tests/integration/test_ingestion_flow.py`
- `tests/integration/test_conversation.py`
- `tests/integration/test_streaming.py`
- `tests/integration/test_concurrency.py`
- `tests/integration/test_escalation.py`
- `tests/integration/test_async_upload.py`
- `.github/workflows/ci.yml` — extra job `integration-tests` с services
  (postgres, redis), markers `pytest -m integration`
- `pyproject.toml` / `pytest.ini` — marker `integration` чтобы можно было
  запускать отдельно

## Implementation sketch

### conftest.py (integration fixtures)
```python
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def integration_postgres():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url()

@pytest.fixture(scope="session")
def integration_redis():
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}"

@pytest.fixture
def integration_app(integration_postgres, integration_redis, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", integration_postgres)
    monkeypatch.setenv("REDIS_URL", integration_redis)
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    from api.app import app
    return app
```

### Example test_ingestion_flow.py
```python
@pytest.mark.integration
async def test_upload_pdf_then_retrieve(integration_client, sample_pdf_path):
    # 1. Upload
    response = await integration_client.post("/api/upload",
        files={"file": sample_pdf_path.read_bytes()},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert response.status_code == 200
    # 2. Wait for async task (if Celery)
    task_id = response.json()["task_id"]
    await wait_for_task(integration_client, task_id, timeout=30)
    # 3. Ask a question matching PDF content
    ask_resp = await integration_client.post("/api/ask",
        json={"question": "Какая политика возврата?", "session_id": str(uuid4())},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert ask_resp.status_code == 200
    body = ask_resp.json()
    assert len(body["documents"]) > 0
    assert any("возврат" in d["content"].lower() for d in body["documents"])
```

### Ollama strategy
Integration tests шарят один Ollama — медленно, но real. Альтернатива:
мокнуть LLM response через `httpx.MockTransport` — быстро, но не ловит
integration bugs. **Compromise**: помечать тесты которые требуют Ollama
маркером `@pytest.mark.requires_ollama`, в CI запускать только с
GitHub Actions matrix с установленной Ollama (self-hosted runner) или
skip'ать.

## CONSTRAINTS
- Integration suite медленный — запускается **отдельно** от unit:
  `pytest -m integration` или `pytest tests/integration/`
- testcontainers требует Docker — CI должен иметь docker-in-docker
- Каждый integration test — полная setup/teardown (fresh DB). Slow, OK.
- В CI: integration — отдельный job, не блокирует unit (параллельно)

## DONE WHEN
- [ ] Директория `tests/integration/` создана с 6 файлами
- [ ] `pytest -m integration -q` запускает только integration тесты
- [ ] `pytest -m "not integration"` запускает существующие 285+ unit
- [ ] CI workflow имеет job `integration-tests` с postgres/redis services
- [ ] Happy-path E2E зелёный (upload PDF → retrieve → answer)
- [ ] Escalation E2E: low-quality → EscalatedTicket создаётся
- [ ] README обновлён: "Running integration tests" section
- [ ] 300+ total passed (285 unit + 15-20 integration)
- [ ] Commit: "Integration test suite for E2E flows (task-122)"
