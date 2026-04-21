# Task 121 — Extract magic numbers to config/settings.py

## Context
POLISH-2 из rec.md. По сверке найдено 55+ вхождений магических чисел и
`# type: ignore` в коде. Примеры из rec.md:
- `rrf_k=60` — RRF-параметр fusion
- `quality >= 70` — threshold качества
- `200` chars для RRF doc key
- `chunk_size=800` — в 3 местах hardcoded

Magic numbers делают tuning невозможным без code change + deploy. Commercial-grade
codebase: константы сверху файла или в settings.

## Goal
Найти все magic numbers в критических путях, вынести в `config/settings.py`
с env-override. Прежнее поведение сохраняется (те же default values).

## Files to change
- `config/settings.py` — добавить новые fields
- `.env.example` — добавить новые env var documentation
- `graph.py`, `vectordb/manager.py`, `chunking.py`, `ingestion/pipeline.py`,
  `agent/prompts.py` — замена literals на `settings.*`
- `tests/` — обновить где тесты hard-code'ят те же литералы

## Known magic numbers (audit from rec.md + общий знающе)

| Current | Source | New setting |
|---------|--------|-------------|
| `rrf_k = 60` | manager.py (RRF fusion) | `rrf_k: int = 60` |
| `quality_threshold = 70` | graph.py | `quality_threshold: int = 70` |
| `200` char RRF key | manager.py | `rrf_doc_key_chars: int = 200` |
| `chunk_size = 800` | chunking.py (3 места!) | reuse existing `chunk_size: int = 800` (уже есть), убрать hardcodes |
| `chunk_overlap = 80` | chunking.py | `chunk_overlap: int = 80` |
| `top_k = 5` | graph.py | reuse `retrieval_top_k: int = 5` |
| `top_k_rerank = 3` | graph.py | `rerank_top_k: int = 3` |
| `max_retries = 3` | resilience calls | reuse existing |
| `pagination limit 100` | api endpoints | `api_default_page_size: int = 100` |
| `escalation_threshold = 0.7` | если hardcoded | `escalation_threshold: float = 0.7` |
| `5` max tool-call loops (task-107) | agent/graph.py | `agent_max_tool_loops: int = 5` |

## Implementation sketch

### config/settings.py (паттерн)
```python
class Settings(BaseSettings):
    # existing...

    # Retrieval tuning
    retrieval_top_k: int = Field(default=5, env="RETRIEVAL_TOP_K")
    rerank_top_k: int = Field(default=3, env="RERANK_TOP_K")
    rrf_k: int = Field(default=60, env="RRF_K")
    rrf_doc_key_chars: int = Field(default=200)

    # Quality / escalation
    quality_threshold: int = Field(default=70, env="QUALITY_THRESHOLD")
    escalation_threshold: float = Field(default=0.7, env="ESCALATION_THRESHOLD")

    # Chunking
    chunk_size: int = Field(default=800, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=80, env="CHUNK_OVERLAP")

    # Agent
    agent_max_tool_loops: int = Field(default=5, env="AGENT_MAX_TOOL_LOOPS")
```

### Replacement (example)
```python
# before (graph.py)
if quality_score < 70:
    route = "human"

# after
if quality_score < settings.quality_threshold:
    route = "human"
```

### .env.example
Добавить секцию:
```
# Retrieval tuning
RETRIEVAL_TOP_K=5
RERANK_TOP_K=3
RRF_K=60
QUALITY_THRESHOLD=70
CHUNK_SIZE=800
CHUNK_OVERLAP=80
```

## CONSTRAINTS
- Default values — **строго** текущие literal. Не "улучшать" случайно.
- Тесты могут hardcode'ить значения для assertions — допустимо через
  `monkeypatch.setattr(settings, "quality_threshold", 50)`
- Не переборщи — оставь literals для:
  - Trivial constants (HTTP codes, unit scales like 1024 для KB)
  - Local one-use numbers
  - Тестов (assertions — ОК, hardcoded data — OK)
- Type-ignore audit — **отдельная работа** (не вкладывай в этот task;
  может быть follow-up). Magic numbers в приоритете.

## DONE WHEN
- [ ] Все Known magic numbers (таблица выше) вынесены в settings
- [ ] Все test suites проходят с тем же поведением
- [ ] `.env.example` обновлён с новыми env vars
- [ ] grep по repo: `rrf_k=60`, `chunk_size=800` встречаются **только**
      в `config/settings.py` и `tests/` (с monkeypatch)
- [ ] README обновлён: секция "Configuration" ссылается на
      `.env.example` как источник истины
- [ ] 285+ passed, ruff clean
- [ ] Commit: "Extract magic numbers to config/settings.py (task-121)"
