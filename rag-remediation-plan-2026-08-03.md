# План незакрытых работ RAG Support Assistant — 2026-08-03

**Статус:** ACTIVE
**Заменяет:** `plan_sol_23_07_26` как источник будущих работ.
**Основание:** открытые DoD из `plan_sol_23_07_26`, активный аудит
`audit_gpt_23_07_26.md` и дополнительные LLM/RAG-риски из
`D:\Dif_Mat\llm_in_proj_rev.md`.

В этот план не перенесены уже локально закрытые implementation-срезы. Их
коммиты и проверки остаются историческим evidence в старом плане и
`AGENT_STATE.md`. Каждый пункт ниже считается закрытым только после указанной
поведенческой проверки; code review или зелёный mock сами по себе не являются
DoD.

## Порядок

```text
1 live release evidence ───────────────┐
2 index lifecycle ─────────────────────┤
3 bounded execution → 4 canonical API → 5 grounding → 6 judge/safety → 7 eval gate
1 + 4 ───────────────────────────────────────────────→ 8 edge security
2–8 ─────────────────────────────────────────────────→ 9 architecture/SLO
1–9 ─────────────────────────────────────────────────→ 10 final verification
```

Первый локальный срез: **2.1 publication inventory wiring only**. В одном
срезе не совмещать inventory record, retention deletion и operator API.

## 1. Закрыть live multi-tenant storage/release evidence

**Источник:** незакрытые DoD старых шагов 1–3. **Приоритет:** P0.

- [ ] На реальном PostgreSQL выполнить upgrade/downgrade всех актуальных
  миграций и двухtenantный restart drill с cold/warm cache, Session/Message/
  Audit read/write/purge и malformed UUID flood.
- [ ] Собрать production image и проверить `pg_dump`/`pg_restore`/`age`, затем
  установить chart в disposable kind/live namespace, пересоздать app pod и
  доказать сохранность uploads, Chroma и traces.
- [ ] Выполнить backup → clean namespace → restore только в disposable DB,
  затем known-query smoke; измерить RPO/RTO и сравнить с 24h/2h либо утвердить
  новые измеренные цели.
- [ ] Зафиксировать release-blocker checklist и артефакты Gate A; без них
  production release остаётся закрыт.

**Проверка:** migration logs, two-tenant matrix, rendered/live PVC evidence,
restore report, known-query result и измеренные RPO/RTO. Live/deploy действия
требуют отдельного явного разрешения владельца.

## 2. Завершить durable ingestion и атомарный lifecycle индекса

**Источник:** незакрытый остаток старого шага 4. **Приоритет:** P1.

- [ ] **2.1:** под действующим tenant lock записывать успешно validated
  versioned collection в trusted retention inventory; ошибка inventory write
  не меняет active manifest, ошибка publish не оставляет опасный live candidate.
- [ ] **2.2:** после успешного publish запускать bounded retention executor с
  настроенным budget; active/previous и unrecorded collections никогда не
  удаляются, частичный delete/prune остаётся наблюдаемым и повторяемым.
- [ ] Добавить явный operator surface для validated rollback и retention с
  tenant scope, dry-run/audit trail и безопасным повтором.
- [ ] Сделать original uploads immutable/versioned и связать их lifecycle с
  job/index version без потери предыдущей рабочей версии.
- [ ] Расширить fault injection до/после embeddings, validation, inventory,
  manifest switch и cleanup; покрыть concurrent same-tenant uploads, duplicate
  job, worker outage/recovery и lock contention.
- [ ] На реальных PostgreSQL/Redis/Celery/Chroma выполнить migrations
  `019`–`021`, worker recovery и advisory-lock contention drills.

**Проверка:** неудачный rebuild не меняет активный индекс; accepted job всегда
имеет terminal state/error; retention удаляет только доказанные bounded
кандидаты; rollback возвращает known-query без auto-create неизвестной
collection.

## 3. Ограничить execution, session state и LLM resource budget

**Источник:** незакрытый старый шаг 5 + новые LLM guards. **Приоритет:** P1.

- [ ] Убрать вложенный per-request `ThreadPoolExecutor`; ввести один deadline и
  bounded executor/job pool, освобождающий capacity только после фактического
  завершения underlying work.
- [ ] Протянуть cooperative cancellation и deadline через provider, retriever,
  reranker и tool boundaries; disconnect/504 не должны оставлять бесконтрольную
  работу или позднюю history/tool mutation.
- [ ] Сериализовать изменения одной session либо ввести optimistic sequence/
  version; передавать `user_id`/`session_id` в normal pipeline для sticky
  experiment assignment.
- [ ] **Новое:** задать конфигурируемые `max_tokens` и `temperature` по LLM-роли
  с безопасными production defaults.
- [ ] **Новое:** ввести общий per-request budget для LLM calls и generated/input
  tokens, общий для retries, grading fallback, fact claims, agentic tools и
  streaming; исчерпание budget не может завершаться `auto`.

**Проверка:** blocking fake provider, repeated timeout, disconnect, concurrent
same-session confirm и budget exhaustion; после terminal результата нет
unbounded orphan work, история упорядочена, лимиты одинаковы во всех путях.

## 4. Сделать один sync/SSE pipeline и durable escalation

**Источник:** незакрытый старый шаг 6. **Приоритет:** P1. **Зависимость:** 3.

- [ ] Сделать LangGraph единственным execution path и источником token/node
  events; sync собирает поток, SSE только транслирует его.
- [ ] Удалить direct streaming RAG и parallel parity: один terminal answer
  определяет citations, scores, route, trace и ровно одну history mutation.
- [ ] Объединить DB ticket, inbox integration и manual escalation в idempotent
  service с transactional outbox.
- [ ] Возвращать `ticket_id` и delivery state; не сообщать о передаче оператору
  до durable insert, а delivery failure делать явным.

**Проверка:** нет второй generation только ради parity; sync/SSE дают один
семантический результат; disconnect/retry не дублируют history или ticket;
каждый terminal `human/error` имеет ticket либо явную durable delivery error.

## 5. Сделать grounding и routing fail-closed

**Источник:** незакрытый старый шаг 7 + уточнённые citation/grading gaps.
**Приоритет:** P1. **Зависимость:** 4.

- [ ] Ввести `verified / unsupported / not_verified`; skip, error, no-context,
  short answer, extractor `NONE` и parse failure никогда не дают factuality 100.
- [ ] Разделить retrieval relevance, answer quality, factual grounding и policy
  safety; не вычислять relevance как производную quality.
- [ ] Разрешать `auto` только при context, `knowledge_gap=false`, отсутствии node
  errors, calibrated factuality и semantic support всех существенных claims их
  фактически указанными документами `[N]`.
- [ ] **Новое:** если лимит 10 claims или обрезка evidence `5 × 3600` оставляют
  существенные утверждения без проверки, весь ответ получает `not_verified`,
  если полнота покрытия не доказана отдельно.
- [ ] Ошибка grader, принудительный возврат top-1 и all-docs-rejected не должны
  молча восстанавливать исходный context; результат — controlled rewrite,
  `not_verified` или human.
- [ ] Проверять hard negatives, near-duplicates, entity-aware retrieval и
  contextual compression только при сохранении safety floors.

**Проверка:** минимум три повторных runs с confidence intervals: context
precision ≥ 0.63, recall ≥ 0.97, FULL ≥ 97, MISS ≤ 1, faithfulness ≥ 0.90,
answer relevancy ≥ 0.92 и unverified auto-rate = 0.

## 6. Добавить независимый judge, agentic parity и pre-response safety

**Источник:** новые пункты LLM-ревью. **Приоритет:** P1. **Зависимость:** 5.

- [ ] Для production закрепить независимость judge от generator/fact-checker по
  model/provider policy; недоступность допустимого judge даёт `not_verified`/
  human, а не эвристический auto.
- [ ] Откалибровать quality/factuality/safety thresholds на versioned
  human-labelled set с правилами разметки, agreement report и cost matrix ошибок
  auto/human; сохранить calibration artifact и model/prompt versions.
- [ ] Удалить agentic `quality_source="fixed"` и константы 80/85/90; tool и
  confirmation paths проходят тот же измеряемый grounding/safety gate.
- [ ] Запускать PII и document prompt-injection checks до выдачи terminal answer;
  policy явно выбирает redact/refuse/human и не полагается на post-response
  monitoring.
- [ ] Зафиксировать входную schema online evaluators и тестами доказать передачу
  всех полей; оставшиеся post-response метрики маркировать только monitoring,
  не runtime protection.

**Проверка:** same-model self-approval запрещён production policy; judge outage,
prompt injection, PII, agentic tool result и malformed evaluator state не могут
дать неподтверждённый `auto`; thresholds воспроизводятся из calibration artifact.

## 7. Сделать regression/evaluation gate честным и fail-closed

**Источник:** незакрытый старый шаг 8 + новый graceful-skip gap.
**Приоритет:** P1. **Зависимости:** 5–6.

- [ ] Executor не читает expected fields для построения answer; baseline берётся
  из merge-base artifact, candidate — из текущего SHA.
- [ ] Расширить path filter на graph, retrieval, ingestion, prompts, providers,
  cache, agentic и streaming; валидировать единую шкалу метрик.
- [ ] Расширить versioned dataset: multi-tenant, multi-turn, claim-citation
  grounding, no-answer, tools, streaming, adversarial documents, PII и durable
  escalation; добавить context recall threshold.
- [ ] Разделить deterministic PR gate и scheduled live provider/independent-
  judge gate; хранить slice metrics, confidence intervals и regression history.
- [ ] **Новое:** evaluator/pipeline/import/provider/judge infrastructure error и
  `skipped=true` завершают release gate ненулевым кодом; запрещены подстановка
  `1.0` и `PASSED (graceful skip)`.

**Проверка:** намеренно испорченные retriever, prompt, route, citation mapping и
evaluation dependency валят gate; mock expected-copy, identical comparison без
исполнения и graceful skip не считаются evidence.

## 8. Закрыть widget и edge/security hardening

**Источник:** незакрытый старый шаг 9. **Приоритет:** P1/P2.
**Зависимости:** 1 и 4.

- [ ] Реализовать widget bootstrap с короткоживущим audience-scoped token,
  `WIDGET_ALLOWED_ORIGINS`, path-specific `frame-ancestors`, строгим
  `postMessage` handshake и reuse `session_id`.
- [ ] Ограничивать фактически полученные ASGI bytes; upload стримить во
  временный файл с atomic rename.
- [ ] Для OIDC требовать `email_verified`, identity `(issuer, subject)` и единый
  tenant email resolver.
- [ ] Запретить placeholder encryption/session secrets и production dev-admin
  bypass; обновить docs dependencies либо оформить точные датированные
  reachability exceptions для каждого high advisory.

**Проверка:** cross-origin Playwright E2E, chunked/oversized body, OIDC linking,
startup secret-negative tests и dependency audit.

## 9. Ограничить cache и декомпозировать orchestration по контрактам

**Источник:** незакрытый старый шаг 10. **Приоритет:** P2. **Зависимости:** 2–8.

- [ ] В Redis fallback добавить TTL/size bound и reconnect with backoff; cache
  namespace включает tenant, index version, prompt version, model ID и
  normalized query.
- [ ] После behavioral contracts выделить `SessionService`, `PipelineRunner`,
  `EscalationService`, `IngestionJobService` и `TraceService`; сохранять public
  API characterization tests и удалять по одному duplicate lifecycle contract.
- [ ] Ввести dashboards/SLO для orphan work, queue age, index publish/retention
  failures, unverified auto-rate, safety blocks, escalation delivery и
  tenant-denied access.

**Проверка:** cache outage/recovery не создаёт unbounded memory или stale
cross-version answer; критические lifecycle paths имеют одного владельца и
сохраняют API contracts.

## 10. Провести итоговую verification и staged rollout

**Источник:** финальный незакрытый rollout DoD старого шага 10. **Выполняется
последним.**

- [ ] Выполнить полный Python 3.11/3.13 suite, coverage, Mypy, Ruff, Bandit,
  dependency audits, migration checks, image/Helm install+restore, sync/SSE E2E,
  deterministic regression и разрешённый live RAG gate.
- [ ] Провести canary на одном tenant с заранее записанными rollback criteria,
  затем staged rollout; проверить SLO и реальный rollback.
- [ ] Подписать release checklist только при закрытых Gate A–D и приложенных
  свежих артефактах; любой skipped, mock-only или stale result оставляет release
  закрытым.

**Done when:** все пункты 1–9 закрыты их собственными evidence; unverified
auto-rate равен нулю; restore/rollback/canary подтверждены; production release
не опирается на graceful skip, фиксированные agentic scores или self-judge без
human calibration.
