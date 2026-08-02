# Project closure

Дата фиксации scope: 2026-07-27.

> ## SUPERSEDED / REOPENED — 2026-08-02 (status @ `2767b9d`)
>
> This closure note is **historical**. Remediation remains **reopened**: the
> project is **not** closed. P0 release-blocker **implementation** is locally
> remediated and mechanically verified at HEAD `2767b9d`, but full audit-plan
> DoD, OPS-01 operational restore DoD, and production release are still open.
>
> **Steps 1–3 partial status:**
> - Step 1 **in progress** — remaining test-first slice: repeated request-ID /
>   trace PK collision (OBS-01).
> - Step 2 **local implementation verified; live PostgreSQL DoD open**.
> - Step 3 **chart/backup runtime locally verified; operational restore DoD
>   open**.
> - Steps 4–10 remain open.
>
> Owner decision unchanged: **no** Hugging Face Space publication target; HF is
> not a required external-user runtime. Users run the service locally (own
> `MISTRAL_API_KEY` + remote embeddings + empty `RAG_RERANKER_MODEL`). Active
> work tracks [`plan_sol_23_07_26`](../plan_sol_23_07_26). Do not delete this
> file; treat it as a dated scope snapshot only.

## Закрываемый scope

Финальный scope — текущий RAG Support Assistant:

- hybrid retrieval, reranking, citations, answer verification и escalation;
- web chat, agent copilot, email/Bitrix channels и confirmation-gated tools;
- JWT/OIDC/RBAC, tenant isolation, audit and encrypted enterprise fields;
- local-first Ollama profile и явные opt-in Mistral/GraceKelly profiles;
- evaluation, online checks, observability, operational CLIs and docs site;
- текущие Docker/Helm/deployment artifacts без заявления о действующем public
  application host.

После публикации closing SHA scope feature-frozen. Новые runtime topology,
quality campaigns и refactors требуют отдельного проекта.

## Final disposition

Решения из `docs/operations/2026-07-21-gate-decisions.md` становятся финальными:

- Q1b nightly/CI floor — `retired` для текущего scope: нет shippable arm;
- multi-replica implementation — `future`: нет принятого SLA;
- `agent/graph.py` split — `retired`: не выполняется как косметический refactor;
- silent-except cleanup — `future/opportunistic`, не активный backlog;
- live GraceKelly/Mistral benchmark — `won't-run` при закрытии без отдельного
  opt-in, staged runtime и provider budget;
- presentation и остальные untracked portfolio artifacts — сохранены локально,
  но не входят в product/repository closure.

`BACKLOG.md` historically reported an empty non-live safe queue. As of
2026-08-02 that is superseded: the audit plan is the sole active backlog
source. Older task specs below remain historical evidence only.

## Обязательные внешние closure gates

- восемь локальных closing commits опубликованы в `master`;
- CI и Pages deployment зелёные на точном closing SHA;
- GitHub issues/PR остаются пустыми после публикации;
- существующий docs-site проверен; public application host не заявляется;
  HF target не входит в проект и не является closure/publication gate.

У проекта нет установленного tag/release pipeline; closure не изобретает новый
release process. Push и любая внешняя публикация требуют явного разрешения
владельца.

## Сохранённые локальные артефакты

Без изменений остаются 12 untracked файлов, включая presentation/explainer,
аудит/планы, architecture diagram, `FLANT_DOGFOOD_FINDINGS.md` и
`scripts/check_architecture_diagram.py`. Они не входят в closing commit.
