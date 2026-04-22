# Arc 7 / Batch H — Verification sweep (2026-04-22)

Repo: `D:\RAG_Support_Assistant`, HEAD при начале sweep = `73dc418` (arc 7 batch G closed).
Codex реализовал все 3 тасков batch H в working tree; ничего не закоммитил.

## Environment check
- `pytest tests/ -q --timeout=300` — **426 passed, 0 failed** за 633s.
- `ruff check .` — **All checks passed**.
- Test delta: 412 → 426 (**+14**), ровно 4+6+4 по spec.
- `git status` — 13 modified + 3 deleted + 10 untracked (включая `codex-tasks/` planning artifacts, `llm/providers/{mistral,gracekelly}.py`, 3 test-файла).

## Per-task verdict

| Task | Verdict | Evidence |
|------|---------|----------|
| 150 Mistral direct API provider | ✅ PASS | `llm/providers/mistral.py`, 3 модели в registry (ministral-3b/8b + mistral-small) с корректными ценами, env `MISTRAL_API_KEY`, 4 теста passing |
| 151 GraceKelly provider + failover | ✅ PASS | `llm/providers/gracekelly.py` с HTTP client на `/api/v1/smart`, health-check `/healthz/ready`, optional Bearer/X-API-Key auth, ProviderUnavailable exception в base, failover chain в runtime, Prometheus `llm_provider_fallback_total` counter, 6+4 тесты passing |
| 152 Routing profiles revamp + cleanup | ✅ PASS | Удалены `llm/providers/{anthropic,openai,gemini}.py`, удалены env vars из .env.example, новые profiles (`local-first` default, `gracekelly-primary` с Ollama fallback, `external-mistral`), 7 existing test-файлов обновлены без регрессий |

## Safeguards check (CRITICAL из meta-ТЗ)

- ✅ **Mistral API key не копирован в .env.example** — placeholder `MISTRAL_API_KEY=changeme` (проверено grep'ом).
- ✅ **.env gitignored** — `.gitignore:9 .env`, `git check-ignore` подтверждает.
- ✅ **No real API calls в тестах** — все 14 новых тестов используют mock HTTP (httpx_mock / respx). Полный pytest не делает сетевых вызовов к Mistral или GraceKelly.
- ✅ **Placeholder fail-fast сохранён** — `changeme` treated как missing; `external-mistral` профиль без real key → startup raise.
- ✅ **Cost guardrail расширен на Mistral** — `daily_cost_limit_usd` применяется к Mistral provider (kind=paid).
- ✅ **GraceKelly cost не атрибутируется** — `cost_usd=0.0` для gracekelly provider в providers.yml.
- ✅ **Failover только local-fallback** — `gracekelly-primary` fallback = ollama (не paid Mistral); silent paid spend предотвращён.

## Structural observations

- `llm/providers/` теперь содержит только `base.py`, `ollama.py`, `gracekelly.py`, `mistral.py`, `runtime.py`, `__init__.py` — clean, 4 backends (1 local, 1 proxy, 1 paid, 1 HTTP aggregator).
- `config/providers.yml` `default_profile=local-first` → zero paid spend без явного переключения.
- Failover chain в `runtime.py` с кешем 5 мин (не проверяем health каждый вызов).
- ProviderUnavailable exception позволяет graceful degradation.

## Commit plan

Следуя batch F/G pattern — **2 коммита**:

1. **Code + docs** — `Arc 7 Batch H: GraceKelly + Mistral providers, drop paid APIs (3 tasks)` — все modified + deleted + untracked кроме `codex-tasks/`.
2. **Archive + verification report** — `Archive Batch H specs + verification report` — move task-150..152 + orchestrator + meta в Archive, keep verification-report-batch-h.md на top level.

## Нет fix-specs — batch H landed clean

Batch H — **второй arc подряд без fix-specs** (batch G тоже landed clean). Стабильность выросла — meta-ТЗ с extracted API contracts и detailed safeguards работает лучше чем open-ended delegation.

## Next arc candidates

Arc 7 продолжается. Потенциальные batch I варианты:
- Continuous learning Phase 2 (online A/B, auto-rollout) — ждёт real traffic signal.
- GraceKelly orchestrate endpoint integration (multi-model consensus, tool-use) — требует более сложного request contract.
- Production backup/restore/chaos — low priority, базовый runbook есть.

См. `codex-tasks/arc-7-proposal.md` за обоснованием.
