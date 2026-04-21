# Task 125 — Arc-6 proposal

## Goal
Проанализировать текущее состояние проекта и предложить 3 кандидата на arc-6 с обоснованием, ориентировочным объёмом и списком идей-тасков. Не писать конкретные спеки — только скелет.

## Context
- Repo: `D:\RAG_Support_Assistant` — production-ready RAG support bot (FastAPI + LangGraph + ChromaDB + Ollama, Postgres, Redis, Prometheus).
- Пройдено 2 арки:
  - **Arc 68-101 (production hardening)** — resilience (retry + breaker + semaphore + timeout), observability (24 метрики + alert rules + correlation ID), health/readiness split, admin UI, multi-tenancy (schema → enforcement → per-tenant ChromaDB), fact-verification node, security (auth hardening, CORS, body size), model routing, tech debt closure.
  - **Arc 102-122 (product + enterprise + polish)** — UX (citations/mobile/WCAG/copilot), RAG intelligence (agentic tools, RAGAS eval, KB gap detection, contextual ingestion), enterprise (OpenTelemetry, SSO/OIDC, encryption at rest), differentiation (KB builder/freshness, auto-categorization, analytics, weekly reports, email channel), code quality (dedup, settings, integration tests).
- Итого 55 закрытых тасков.
- Tests: 293 passed. Ruff clean. Multi-tenant deploy-safe.
- Контекст продукта: single-user local проект (Julia Edomskikh, data engineer; Королёв МО). Нет команды, нет реальной customer-support нагрузки. Приоритет — полезность как песочница для инженерных экспериментов и потенциальный production-слот, а не scaling под thousands of users.

## Deliverables
`codex-tasks/arc-6-proposal.md` со структурой:

```
# Arc-6 proposal

## Current state recap
(1-2 абзаца: что есть, что закрыто)

## Gap analysis
(5-10 bullets: что реально не сделано. Примеры для ориентира — не обязательно использовать:
hybrid search / re-ranking / HyDE, cost tracking, load/chaos testing, disaster recovery,
multilingual, voice/Slack/Teams, continuous learning from feedback, Claude API as alternative backend,
backup/restore runbooks, canary deploys)

## Arc-6 candidate A — <название>
- Goal: …
- Motivation: …
- Ideas (5-10):
  1. [one-liner] → artifact
  2. …
- Estimated scope: N task-специфик, ~M часов
- Expected impact: …
- Risks / complications: …

## Arc-6 candidate B — <название>
(то же)

## Arc-6 candidate C — <название>
(то же)

## Recommendation
Выбрать один, обосновать через: impact × novelty × complexity × user preference.
```

## Acceptance
- 3 различных направления — пересечение содержания не более 30% (грубо: не 3 варианта одной темы).
- Каждая идея — one-liner + ожидаемый артефакт (файл / метрика / ability).
- Scope estimates реалистичные (сравнимые с arc 68-101 и 102-122).
- Рекомендация аргументирована, не "все три хороши".
- Файл на русском.
- Сохранён в `codex-tasks/arc-6-proposal.md`.

## Notes
- **НЕ писать конкретные task-спеки** — это следующий шаг, не этот.
- **Не внедрять ничего** в код.
- **Не трогать существующие файлы** — только новый proposal.
- Учитывать profile пользователя: single-user, локально, Windows, Python 3.13, limited Ollama ресурсы (нет GPU-ферм), interest в data engineering / analytics.
- Кандидаты-ориентиры (можно использовать, можно заменить): Cost Optimization, Advanced RAG v2 (hybrid/re-rank/HyDE/query-rewrite), Production Operations (chaos/load/DR/backup), Continuous Learning (feedback loop/online eval/prompt tuning), Multi-channel Expansion (Slack/Teams/voice/WhatsApp), Alternative Backends (Claude API toggle, Gemini toggle, model comparison).
- Не ограничиваться этим списком — если видишь что-то более осмысленное для текущего состояния, предлагай.
- Избегать direction'ов, которые требуют инфраструктуры вне single-user scope (например, "multi-region deployment" — overkill).
