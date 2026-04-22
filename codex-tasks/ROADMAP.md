# RAG Support Assistant — post-arc roadmap (CLOSED 2026-04-21)

Слияние `commercial-upgrade-plan.md` + `rec.md` с учётом фактического
состояния кода после арка 68-101. Каждый открытый пункт переработан в
Codex-спеку; закрытые пункты сюда **не включены** (см. `Archive/`).

> **Status (2026-04-22):** все 21 task arc 102-122 и follow-up fix-tasks
> 130/131/132 реализованы, закоммичены и заархивированы.
> Current repo state после закрытия follow-up'ов и Batch F: 393 passed,
> Ruff clean. Gaps из verification sweep (task-123) закрыты коммитом
> `ee5ff51`; у этого roadmap больше нет pending fix-tasks.

## Baseline (на момент 2026-04-20)
- 71 коммит в арке 68-101, 222 теста passing, ruff clean
- Arc закрыл: Phase 0 (security hardening), Phase 1 Foundation почти
  полностью (DB-1..4, AUTH-1, AUTH-2, ASYNC-1/2, Redis cache), Phase 4
  OBS-2/3 (Prometheus + Alertmanager), COMP-1/2/3 (audit, PII, retention),
  DEPLOY-1/2/3 (Helm, CI, graceful shutdown), multi-tenancy Phase 1-4,
  UX-2/3/4 (suggested Q, talk-to-human, copy+timestamps), FEAT-1/2
  (semantic chunking on, HyDE feature-flagged), RQ-1/2 (Langfuse, eval gate).

## Batches (ALL CLOSED)

### Batch A — UX Commercial Grade (Phase 2) ✅
Быстрые visible wins. Приоритет 1 — дают наиболее заметный product-lift.
- [task-102] — inline citations `[N]` + source panel ✅
- [task-103] — mobile breakpoints + tap targets ✅
- [task-104] — WCAG AA audit — ✅ static review закрыт в арке, real axe-core/keyboard audit закрыт follow-up [task-132](Archive/task-132-run-axe-audit.md)
- [task-105] — upload progress bar, error recovery retry, onboarding ✅
- [task-106] — operator dashboard + context panel (COPILOT-1/2) ✅

### Batch B — Advanced RAG & Intelligence (Phase 3) ✅
- [task-107] — LangGraph tool-use framework + multi-step + confirmation ✅
- [task-108] — nightly eval pipeline + drift alert ✅
- [task-109] — auto-ticket на "не знаю" кластеры ✅
- [task-110] — активация contextual headers в ingestion ✅

### Batch C — Enterprise Hardening (Phase 4) ✅
- [task-111] — OTel SDK для distributed tracing ✅
- [task-112] — SSO через authlib (Google/Azure OIDC) ✅
- [task-113] — pgcrypto для sensitive fields ✅

### Batch D — Product Differentiation (Phase 5) ✅
- [task-114] — resolved tickets → draft KB articles ✅
- [task-115] — stale-doc monitoring + alerts ✅
- [task-116] — auto-tag docs при upload ✅
- [task-117] — top topics, resolution rate — ✅ cost tracking исправлен follow-up [task-130](Archive/task-130-fix-analytics-cost-calc.md)
- [task-118] — Slack/email weekly digest ✅
- [task-119] — IMAP/webhook email channel — ✅ poller/webhook/tenant delimiter исправлены follow-up [task-131](Archive/task-131-fix-email-channel.md)

### Batch E — Code Quality & Integration Tests ✅
- [task-120] — снять дубли root-level `graph.py`/`state.py` — ✅ (manager.py — двухслойная архитектура, не дубликат)
- [task-121] — вынести magic numbers в settings ✅ (fixed settings drift post-hoc)
- [task-122] — end-to-end integration suite (PROD-4) ✅

## Closing tasks (post-arc)

- [task-123] — verification sweep arc 102-122 → `verification-report.md` ✅
- [task-124] — README update для arc 102-122 ✅
- [task-125] — arc-6 proposal → `arc-6-proposal.md` ✅
- [task-126] — hygiene & consistency audit → `cleanup-report.md` ✅
- [task-127] — CI pipeline (.pre-commit + GitHub Actions ci.yml) ✅
- [task-128] — `docs/CHANGELOG.md` ✅
- [task-129] — `docs/operations/backup-restore.md` ✅

## Closed follow-up fixes

- [task-130](Archive/task-130-fix-analytics-cost-calc.md) — cost calculation в analytics dashboard закрыт коммитом `ee5ff51`
- [task-131](Archive/task-131-fix-email-channel.md) — email channel fix закрыт коммитом `ee5ff51`
- [task-132](Archive/task-132-run-axe-audit.md) — real axe-core audit + keyboard test + `docs/a11y/` закрыт коммитом `ee5ff51`

## DONE WHEN (для всего roadmap)

- [x] 21 базовая задача arc 102-122 реализована
- [x] 293 теста passing (>280 target)
- [x] README обновлён с новыми фичами/env vars (task-124)
- [x] axe-core: 0 critical/serious — follow-up [task-132](Archive/task-132-run-axe-audit.md)
- [ ] Lighthouse mobile ≥90 — отдельный performance sweep, не часть закрытия этой roadmap
- [ ] Resolution rate ≥50% (если появится production трафик) — постпродакшн

## Next arc (Arc 7)

- [arc-7-proposal.md](./arc-7-proposal.md) — новый proposal с кандидатами G/H/I и рекомендацией брать Batch G.
- Batch G — provider abstraction: registry `config/providers.yml`, unified `llm/providers/*`, provider-aware cost accounting, mock-by-default benchmarking, admin Providers tab.
- Batch H — continuous learning phase 2 остаётся deferred до появления большего production traffic и A/B signals.
- Batch I — backup/restore/chaos остаётся deferred: базовый runbook уже есть, но расширение не критично для current single-user setup.
