# План доработок по аудиту 18.07.26 — выполнено 6 из 8 (+1 вне плана)

Источник: `audit_fable_18_07_26.md`. Прод-дефолты (retrieval/latency/routing)
ни одна задача не меняет. Задачи 1–5 — Windows-doable без внешних ресурсов;
6–8 — за гейтами (Mac / SLA / явное решение).

## Goal

Закрыть три слепых пятна процесса (P1, N1, N2), убрать мелкий carried-долг
(N3, N5, N7) и удерживать гейты на тяжёлом остатке (Q1-прогон, multi-replica,
C1) до выполнения их условий.

## Tasks

### Сейчас (короткие, по приоритету)

- [x] ~~**1. P1 — push `b5978f0`**~~ — ВЫПОЛНЕНО, origin = `343a742`.
  → Verify: `git push` → CI на новом HEAD success целиком (`gh run watch`).
  *Гейт: push = решение Юли (вне /auto).*

- [x] ~~**2. N1 — оживить coverage-гейт**~~ — ВЫПОЛНЕНО (`e6b49bc`, не запушен).
  Замер до включения: **73%** unit-scope, порог оставлен 70 (запас намеренный).
  Блокер вне аудита: `pytest-cov` не было в `requirements-dev.lock` при
  `--require-hashes` → добавлен `pytest-cov==7.1.0`, перекомпиляция без
  чужих бампов, `pip-audit` по dev-lock чист. Гейт закреплён тестом
  (мутационно проверен). Исходная формулировка: в `ci.yml` test-unit добавить
  `--cov --cov-report=term` в одну ногу матрицы (3.13); `fail_under=70`
  подхватится из pyproject. Если реальное покрытие упало ниже 70 — не
  занижать гейт молча, а показать число Юле.
  → Verify: CI-лог печатает процент; тест-джоб красный при <70 (проверить
  локально сломав порог на 99 в тестовом прогоне нельзя — верить CI-логу).
  ~1 час.

- [x] ~~**3. N2 — regression-eval на push**~~ — ВЫПОЛНЕНО (`e6b49bc`).
  Перед включением джоб прогнан локально его же командой: exit 0, 35 кейсов,
  `gate.passed=true`, 0 регрессий. Закреплён тестом. Исходная формулировка: убрать `if: pull_request` /
  добавить push-ветку с тем же `dorny/paths-filter` (фильтр уже написан).
  → Verify: на следующем push, трогающем `config/settings.py` или
  `agent/prompts.py`, джоб появляется в run'е и зелёный; на docs-only push —
  skipped. ~30 мин.

- [x] ~~**4. N5 — архивировать AGENT_STATE.md**~~ — ВЫПОЛНЕНО: 136 KB → 16.8 KB
  (11 KB после выноса + новый handoff-блок). Вынесены 22 датированных блока
  плюс майские `Last Verified Gates` и `Next Step`. Сверка с `git show HEAD:`:
  31 блок = 7 корень + 24 архив, потеряно 0. Исходная формулировка: superseded-блоки (июнь и
  старше) → `docs/sessions/agent-state-archive-2026H1.md`; в корне оставить
  2 верхних блока + ссылку на архив.
  → Verify: `pytest tests/test_docs_quality.py` passed; файл ≤ 30KB;
  содержимое архива = вырезанное 1:1 (diff).  ~40 мин.

- [x] ~~**5. N3 + N7 — docs-хвосты одним коммитом**~~ — ВЫПОЛНЕНО. N3 сверен
  построчно с `_cookie_auth_origin_ok`. N7 — выбрана шапка SUPERSEDED, а не
  построчные чекбоксы (60+ RQ-пунктов дёшево не подтвердить; это указано в
  самой шапке). Исходная формулировка: (а) в `docs/DEPLOYMENT.md`
  абзац «cookie-auth за reverse-proxy: ingress обязан пробрасывать Host,
  иначе Origin-гейт режет state-changing запросы браузерных UI»;
  (б) `commercial-upgrade-plan.md` — проставить выполненные RQ-чекбоксы или
  шапку «superseded → docs/audits/».
  → Verify: `pytest tests/test_docs_quality.py` passed. ~40 мин.

### Гейтованное — решения 2026-07-21 (делегированы агенту)

- [x] ~~**6. Q1 heavy-прогон на Mac**~~ — ВЫПОЛНЕНО 18.07, вердикт NO-SHIP по
  всем 7 плечам, дефолты не тронуты. Evidence:
  `docs/operations/2026-07-18-q1-context-precision-ab-results.md`.
  → Verify: отчёт-артефакт в `docs/operations/`, вердикт по критериям;
  после — решение по nightly RAGAS drift-job (Q1b).

- [x] ~~**7. N4 — policy**~~ — РЕШЕНИЕ 2026-07-21 (hybrid, см. AGENT_STATE Update-7):
  - **Tracked оставляем** (agent memory + technical transparency): root kitchen
    (`AGENT_STATE.md`, `BACKLOG.md`, `AUTOPILOT.md`, research/fable notes),
    `docs/sessions/**`, `docs/operations/**`, `docs/audits/**`.
  - **Pages:** только не-kitchen guides. Kitchen dirs:
    `plans/ research/ operations/ a11y/ superpowers/ sessions/` — **не
    публикуются**. Product audits в `docs/audits/` остаются на Pages как
    витрина (проверено: без LAN-IP / secret-path маркеров).
  - **Не делаем** `git rm --cached` history rewrite — риск/польза плохие;
    репо публичный, история уже есть.
  - Process-аудиты fable/plan → `docs/operations/` (kitchen).

- [x] ~~**8. Долгие линии**~~ — РЕШЕНИЯ 2026-07-21:
  - **Q1b** (nightly RAGAS + CI quality floor) — **DEFER**. Q1 NO-SHIP: нет
    плеча с Δprecision без FULL/MISS регрессии → floor/drift на старом
    precision 0.51 baseline без shippable arm = шум. Открыть когда появится
    SHIP-arm или явный новый baseline.
  - **multi-replica impl** — **DEFER**. Design готов; без реального SLA
    (load/HA) не начинать (см. design doc headline).
  - **C1** распил `agent/graph.py` — **DEFER**. Broad refactor без feature
    trigger запрещён аудитами; точечно только попутно с работой в модуле.
  - **L1** silent-except — **точечно, попутно** (не отдельная волна).

## Вне плана (найдено при исполнении, 19.07)

- [x] ~~**T2 — мина fastapi обезврежена**~~ — ВЫПОЛНЕНО. Update-3 записал 5
  падающих тестов как «перебор `app.routes`»; для `test_http_metrics` (3 из 5)
  это неверно — оказался **продакшен-баг**: с fastapi 0.138 `path_format`
  теряет префикс роутера, лейбл `endpoint` у всех метрик молча меняется, а
  одноимённые маршруты разных роутеров схлопываются в одну серию. Фикс
  `_route_mount_prefix` без ветвления по версии, проверен в venv на 0.136.1
  (no-op, байт-в-байт) и 0.138.1 (чинит). Тесты владельца переведены на
  публичную `iter_route_contexts` с fallback. Детали — AGENT_STATE Update-4.

## Done When

- [x] ~~1–5 выполнены, CI зелёный, coverage-число известно и ≥70~~ — ВЫПОЛНЕНО:
  CI run 29660377386 success (12/12), **coverage 73.30%**, порог поднят 70 → 72
  против CI-замера.
- [x] ~~6 прогнан при первом свободном Mac-окне, вердикт задокументирован~~ —
  ВЫПОЛНЕНО 18.07, NO-SHIP.
- [x] ~~7 имеет явное решение~~ — ВЫПОЛНЕНО 2026-07-21: hybrid N4 + DEFER
  Q1b/multi-replica/C1. Текст: `docs/operations/2026-07-21-gate-decisions.md`
  и AGENT_STATE Update-7.

## Notes

- Non-goals без новых данных: factcard в дефолт, авто-роутер, multi-worker
  без externalization, broad-рефакторы (подтверждено обоими аудитами).
- Process-аудиты fable/plan: **закоммичены** в kitchen
  `docs/operations/2026-07-18-audit-fable.md` и
  `docs/operations/2026-07-18-plan-fable.md` (N4 hybrid, 2026-07-21).
  Корневые untracked-копии удалены.
- Задачи 2–5 при выполнении в `/auto`: локальные коммиты по одному на задачу,
  push по правилу auto-mode-own-the-push.
