# Task 174 — GraceKelly runtime smoke harness

## Goal
Закрыть Known gap Arc 7 Batch H/K: на данный момент GraceKelly provider покрыт только mock-тестами, никогда не проходил e2e против реального запущенного GraceKelly на `http://127.0.0.1:8011`. Нужен повторяемый smoke-скрипт который валидирует: healthz → smart dispatch → tool loop → schema dispatch → streaming → failover на Ollama → Prometheus cost/fallback метрики populated.

## Context
- GraceKelly — локальный orchestrator в `D:\GraceKelly\` (отдельный проект), слушает `http://127.0.0.1:8011`. Endpoints: `/healthz/ready`, `/api/v1/smart` (simple dispatch), `/api/v1/orchestrate` (advanced, tool-use/schema).
- В RAG-проекте GraceKelly интегрирован как `llm/providers/gracekelly.py`. Активируется через `LLM_PROVIDER_PROFILE=gracekelly-primary` (default fallback chain: gracekelly → ollama).
- `agent/graph.py` использует provider-native tool loop (`_run_provider_tool_loop`) и schema output (`_invoke_with_schema`) с safe fallback на строковый парсинг.
- Prometheus метрики, которые должны инкрементиться: `llm_cost_usd_total{provider="gracekelly",model=...,tenant=...}` (должно быть 0 USD — локальный proxy), `llm_provider_fallback_total{from_provider,to_provider,reason}` при намеренно сломанном GraceKelly.
- Smoke **НЕ** идёт в CI — это manual script, запускается когда у юзера GraceKelly живой.

## Deliverables
- `scripts/gracekelly_smoke.py` — standalone CLI:
  - args: `--gracekelly-url` (default `http://127.0.0.1:8011`), `--rag-url` (default `http://127.0.0.1:8000`), `--tenant` (default `smoke-test`), `--verbose`.
  - checks, в порядке (каждый — log line с ✓/✗ + latency):
    1. `GET {gracekelly-url}/healthz/ready` → 200.
    2. Activate profile: RAG должен быть запущен с `LLM_PROVIDER_PROFILE=gracekelly-primary`; скрипт проверяет через `GET {rag-url}/api/admin/providers` что active profile содержит `gracekelly`.
    3. Simple ask: `POST {rag-url}/api/v1/ask` с коротким вопросом, assert response.provider == "gracekelly", response.model populated, response.text non-empty.
    4. Tool use: complex multi-step вопрос, assert response содержит tool_calls trace steps (проверить через `GET {rag-url}/api/v1/traces/{trace_id}`).
    5. Schema output: route classification — assert определённая route (auto/fact/support), не fallback.
    6. Streaming: `POST {rag-url}/api/chat/stream` (SSE), assert получены ≥3 incremental chunks, assert final `done: true`.
    7. Prometheus cost: `GET {rag-url}/metrics`, regex `llm_cost_usd_total{provider="gracekelly".*?} (\d+\.\d+)` → value увеличился относительно baseline (до smoke).
    8. Failover: скрипт временно блокирует GraceKelly (через `--simulate-down`: POST фейкового endpoint'а или env flag). Следующий ask → должен упасть на Ollama; Prometheus `llm_provider_fallback_total{from_provider="gracekelly",to_provider="ollama",reason="unavailable"}` инкрементится.
  - exit codes: 0 all green, 1 healthz failed, 2 smart ask failed, 3 tool loop failed, 4 schema failed, 5 streaming failed, 6 metrics failed, 7 failover failed.
  - pretty-print итог в таблице: step / status / latency_ms.
- `docs/operations/gracekelly-smoke.md`:
  - preconditions: `D:\GraceKelly\` запущен и слушает 8011; RAG запущен с `LLM_PROVIDER_PROFILE=gracekelly-primary`; `.env` содержит `GRACEKELLY_URL=http://127.0.0.1:8011`; baseline Prometheus scrape сделан.
  - пример вывода smoke-скрипта.
  - troubleshooting: GraceKelly 503 → проверить `D:\GraceKelly\` logs; RAG на ollama вместо gracekelly → проверить `/api/admin/providers`; failover не триггерится → проверить `--simulate-down` path.
- `docs/CHANGELOG.md` — запись про smoke harness.

## Acceptance criteria
- [ ] `python scripts/gracekelly_smoke.py --verbose` завершается exit 0 при работающем GraceKelly на 8011 и RAG на 8000 с `LLM_PROVIDER_PROFILE=gracekelly-primary`.
- [ ] Принудительно остановленный GraceKelly (`docker stop` или `--simulate-down` флаг) → skрипт завершается exit 7, stderr: "step 8 failover: expected fallback counter increment, got 0".
- [ ] Prometheus scrape после smoke содержит non-zero `llm_cost_usd_total{provider="gracekelly",...}` (cost 0.0 **тоже** non-zero-increment counter — rate up from baseline value в лог-messaging).
- [ ] `ruff check scripts/gracekelly_smoke.py` clean.
- [ ] Скрипт не делает mock-вызовов: все HTTP реальные, все metrics real parse.
- [ ] Скрипт не требует `pytest` / не ломает unit suite.

## Notes
- Тест НЕ ставить в CI. Manual-only. `README.md` не изменять; instruction только в `docs/operations/gracekelly-smoke.md`.
- Не коммитить dummy `GRACEKELLY_API_KEY`; если smoke требует Bearer auth, читать из `os.getenv("GRACEKELLY_API_KEY")`, fail-fast с understandable error если пусто.
- Failover simulation (`--simulate-down`) — самый простой путь: запустить smoke с подменённым `GRACEKELLY_URL=http://127.0.0.1:9999` (заведомо недоступный), тогда `llm/providers/gracekelly.py` поднимет `ProviderUnavailable`, runtime переключится на Ollama. Не нужно останавливать реальный GraceKelly.
- `/api/v1/traces/{trace_id}` — endpoint существует; проверить что возвращает steps с `tool_calls` для complex-multi-step case.
- Streaming endpoint SSE: использовать `httpx.stream(...)` + `for line in r.iter_lines()`; timeout 30s, assert `done: true` в последнем chunk.
- Если какой-то из 8 шагов не применим к текущему состоянию кода (например, tool-use не wired на все routes) — пометить warning, не fail; but сделать это явно в коде скрипта (`SKIPPED` state, не `FAILED`).
- Запуск GraceKelly — ответственность юзера; скрипт ругается early с clear message "GraceKelly not reachable at {url}, start D:\GraceKelly\ first".
