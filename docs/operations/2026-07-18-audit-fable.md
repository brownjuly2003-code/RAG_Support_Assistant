# Аудит RAG_Support_Assistant — 18.07.26 (Fable)

**Аудитор:** Claude Fable 5 (Anthropic)
**Дата:** 2026-07-18 (вечер)
**HEAD локально:** `b5978f0` (`ui: logout buttons in admin/agent + retarget stale localStorage test assert`) — **НЕ запушен**
**origin/master:** `48e97ab` — CI run 29631430111 **success целиком**, Pages deploy success
**Предыдущий аудит:** `audit_grok_16_07_26.md` (16.07, HEAD `0b0234c`) + волна-2 фиксов по нему (18.07, пакет `c15a5a9..48e97ab`)

---

## 0. Методология и границы

Дельта-аудит поверх `audit_grok_16_07_26.md`: (1) верификация закрытий волны-2
по каждому finding'у grok-реестра, (2) собственный проход по гейтам, CI,
безопасности, репо-гигиене в поиске нового. Ландшафтная часть (архитектура,
история findings до 16.07) у grok актуальна — не дублируется.

### Что прогонялось вживую на этой машине

| Проверка | Результат |
|---|---|
| `ruff check .` (конфиг проекта) | **PASS** — All checks passed |
| `pytest tests/test_admin_ui.py` (вкл. ретаргет из `b5978f0`) | **11 passed** |
| `pytest tests/test_session_auth_cookie.py + test_docs_quality.py + test_precommit_config.py` | **34 passed** |
| `pip-audit --strict --require-hashes` (+3 док-ignores) по `requirements.lock` | **No known vulnerabilities, 1 ignored** |
| то же по `requirements-dev.lock` | **No known vulnerabilities, 1 ignored** |
| `bandit -r . -c pyproject.toml` (документированная команда) | **0 High / 0 Medium** / 53 Low |
| `gh run list` | CI на `48e97ab` success; Pages success; weekly-report по расписанию работает |
| git-инвентаризация | ahead 1 (`b5978f0`); untracked = 7 известных не-секретных файлов |
| Метрики | 509 коммитов; 74 endpoint-декоратора (+2 = `/api/auth/session|logout`); 153 test-файла; alembic 17 ревизий / 1 head |

Все тесты — с проектной Windows-гочей `-p no:schemathesis --basetemp=.tmp/pytest`.

### Что НЕ гонялось (и почему)

- Полный pytest / mypy strict — локально глобальный Python 3.13.7 без project
  venv (lock = 3.11 + Linux); py launcher вообще не имеет 3.11. Источник истины —
  CI: свежий полный success на `48e97ab` сегодня (unit 3.11+3.13, integration,
  type-check, lint, security, pre-commit, migrations, helm).
- RAGAS / heavy embed / Q1-прогон — Mac занят DE_project-стендом; прогон остаётся
  гейтованным (см. R-2).
- LOC-числа ниже — физические (`wc -l`); у grok — bandit-LOC (без пустых/комментов).
  `agent/graph.py` не менялся с 18.06 — «рост» 2317→2652 это разница методик, не код.

---

## 1. Executive Summary

Проект в **пике формы за свою историю**: все HIGH-находки аудита 16.07 закрыты
кодом и данными за два дня, CI полностью зелёный, оба lock-файла чисты на
сегодняшние advisory, cookie-auth прошёл адверсариальный ревью. Волна-2
выполнена дисциплинированно: дефолты не тронуты, NO-SHIP-культура сохранена.

Найденное новое — не про код, а про **дыры в страховочной сетке CI** (N1, N2)
и **процесс** (P1): два гейта, которые выглядят работающими, но фактически не
срабатывают, и один верифицированный, но незапушенный коммит.

**Оценка: ≈9.0 / 10** (16.07 было 8.9). Оговорка: адверсариальной перепроверки
субагентами не было (параллель — только по явному разрешению), оценка
консервативная. Потолок держат: недоказанное live-качество (context_precision
0.51, прогон ждёт Mac), single-replica топология (design готов, impl по SLA),
мёртвый coverage-гейт.

### Топ прямо сейчас

| # | ID | Sev | Суть |
|---|---|---|---|
| 1 | **P1** | PROCESS | `b5978f0` (logout-хвост S1) сидит локально, ahead 1 — CI его не видел. Локально верифицирован (11 passed + ruff). Нужен push. |
| 2 | **N1** | MEDIUM | Coverage-гейт мёртв: CI гоняет pytest **без `--cov`**, `fail_under=70` из pyproject нигде не применяется. Последний честный замер — 70.02% от **2026-04-29** (2.5 месяца назад). |
| 3 | **N2** | MEDIUM | `regression-eval` в CI — `if: github.event_name == 'pull_request'`, а рабочий процесс = прямые пуши в master (последний PR — №1 от 30.05) → джоб **фактически никогда не запускается**. |
| 4 | **R-2** | HIGH (product, carried) | context_precision ≈0.51 — единственная HIGH-находка grok, закрытая только харнессом: Q1-прогон ждёт свободного Mac. |

---

## 2. Верификация волны-2 (закрытия grok-findings)

Каждый пункт перепроверен по коду/прогонам, не по заявлениям handoff'а.

| ID (grok) | Заявлено | Моя верификация | Вердикт |
|---|---|---|---|
| **D1** dep-CVE (aiohttp/cryptography) | закрыт `2263a8c` | pip-audit оба lock прогнан сегодня вечером: чисто, 1 ignored; свежих advisory после утреннего пуша нет | **ЗАКРЫТ** ✔ |
| **S1** токены в localStorage | закрыт `3cac073` + хвост `b5978f0` | `test_session_auth_cookie.py` 9 passed; `test_admin_js_served` теперь ассертит отсутствие `localStorage.setItem`; читал `_cookie_auth_bridge`/`_cookie_auth_origin_ok` и `session_auth.py` — Origin-гейт на unsafe-методах на месте, SameSite-Lax-нюанс SSO задокументирован в docstring | **ЗАКРЫТ** ✔ (см. N3 — proxy-нюанс) |
| **T1** хрупкий route-тест | закрыт `2263a8c` | тест переведён на OpenAPI; в прогоне admin_ui/guards не флапает | **ЗАКРЫТ** ✔ |
| **Q2** latency budgets | закрыт `694dbc0` | `docs/OPERATIONS.md:232` «Latency budgets & timeouts», рекомендация `RAG_ASK_BUDGET_SEC=300`, дефолт 0 не тронут | **ЗАКРЫТ** ✔ (docs) |
| **Q1** precision + нет quality-гейта | харнесс `5b6c157` | `scripts/ab_context_precision.py` + run-plan прочитаны: 8 плеч вокруг D2, переиспользование существующих стадий, SHIP-критерии вшиты (Δprec ≥ +0.05, recall ≥ 0.90, FULL/MISS без регрессий), 7 mock-тестов | **ПОДГОТОВЛЕН**, прогон гейтован Mac'ом |
| **A1/S4** single-replica | design-doc `ee82fea` | `docs/plans/2026-07-18-multi-replica-design.md`: 22 позиции state с file:line; ключевые поправки к аудиту верны по коду (сессии уже Postgres, LLM-кэш уже Redis; реальные блокеры — rate limiter без storage и confirm-actions; telegram_bot single-instance) | **DESIGN ГОТОВ**, impl только по SLA |
| **C1** god-modules | не трогали | graph.py 2652 / app.py 1848 / _base_manager 1338 / settings 1105 / conversation 1023 (физ. строк); graph.py не менялся с 18.06 | **ОТКРЫТ**, гейт «только по явному решению» соблюдён |

Адверсариальный ревью S1 волны-2 (Origin-гейт, вакуумные cookie-тесты) — оба
SHOULD-FIX реально в коде/тестах, не только в CHANGELOG.

---

## 3. Новые находки (18.07, Fable)

### P1 — Незапушенный верифицированный коммит — PROCESS

`b5978f0` (logout-кнопки admin/agent + ретаргет `test_admin_js_served`) сделан
сегодня 12:03, ahead 1 от origin. Diff чистый: кнопка → существующий
`POST /api/auth/logout`, без новых эндпоинтов; тест перестал держаться на
legacy-строке. Я прогнал `test_admin_ui.py` — 11 passed, ruff clean. Но CI
этот коммит не видел, и остаток дня он ничем не защищён (диск/reset).
**Действие:** push (решение владельца; после push проверить CI как обычно).

### N1 — Coverage-гейт не применяется нигде — MEDIUM (process)

`pyproject.toml` держит `[tool.coverage.report] fail_under = 70` с комментарием
«Honest baseline: 70.02% verified 2026-04-29». Но:

- `ci.yml` test-unit: `pytest tests/ -q --ignore=tests/integration -p no:cacheprovider` — **без `--cov`**;
- `[tool.pytest.ini_options]` — `addopts` нет, coverage автоматически не включается;
- локальный `htmlcov/` — от 29.04.

То есть с 29 апреля (≈80 дней, сотни коммитов) покрытие никем не меряется, а
гейт создаёт ложное ощущение защиты (grok в §5 тоже считал его действующим).
**Fix (дёшево):** добавить `--cov --cov-report=term` в одну ногу матрицы
test-unit (3.13) — `fail_under` подхватится из pyproject; либо честно удалить
гейт из pyproject. Первое лучше: инфраструктура вся есть.

### N2 — regression-eval никогда не запускается — MEDIUM (process)

Джоб `regression-eval` (mock-runtime, детерминированный) гейтит регрессии
промптов/настроек/curated-датасета, но условие `if: github.event_name ==
'pull_request'` + рабочий процесс «прямые пуши в master» (PR в репо один, от
30.05) = джоб не запускался ни разу за всю волну июньских-июльских изменений,
включая правки `config/settings.py` из dogfood-батча (path-фильтр бы сработал).
**Fix:** разрешить джоб и на `push` в master с тем же `dorny/paths-filter`
(фильтр уже написан) — стоимость нулевая, mock-runtime лёгкий.

### N3 — Origin-гейт cookie-auth сравнивает с raw Host — LOW (security/ops)

`api/app.py:1827`: `urlparse(origin).netloc == request.headers.get("host")`.
За reverse-proxy/ingress (а Helm-деплой — ровно этот случай) `Host`, который
видит uvicorn, может не совпадать с публичным хостом из браузерного `Origin`
(зависит от `proxy_set_header`/ingress-конфига) → state-changing запросы
браузерных UI молча потеряют cookie-auth (или, при переписывании обоих, гейт
останется корректным — надо знать конфиг). Локально/со стандартным
`proxy_set_header Host $host` работает. **Fix:** пока — абзац в
`docs/DEPLOYMENT.md` («ingress обязан пробрасывать Host»); при появлении
реального прода за proxy — поддержать `X-Forwarded-Host` за настройкой.

### N4 — Внутренняя кухня tracked в публичном репо — INFO (policy, решение владельца)

В публичном GitHub лежат: `AGENT_STATE.md` (136KB плотного handoff'а),
`fable_com.md`, `next-session-fable-hardening.md`, `research_adaptive.md`,
`audit_grok_16_07_26.md`, `commercial-upgrade-plan.md`, `BACKLOG.md`,
`AUTOPILOT.md`, `docs/audits/` (8 аудитов), `docs/sessions/`. Секретов там нет
(проверено выборочно), и историческая практика проекта — сознательная
(evidence-culture как витрина; grok это даже хвалил). Но по действующему
глобальному правилу владельца (2026-07-09, после инцидента AB_TEST) внутренние
аудиты/планы наружу не уезжают. Противоречие надо разрешить **решением, а не
дефолтом**: (а) оставить как витрину — тогда зафиксировать исключение для
этого репо; (б) вынести хвосты (AGENT_STATE, next-session, research) из
tracked. Сам не трогаю. Новые файлы этого аудита оставлены **untracked**.

### N5 — AGENT_STATE.md продолжает расти — INFO (carried I2)

136KB, сегодня +4KB. Верхний START-HERE-блок отличный; всё ниже июньского
уровня — superseded и продублировано в CHANGELOG/docs/operations. Архивация
старых блоков (в `docs/sessions/` или `archive-legacy/`) снизит и вес N4.

### N6 — Локальная верификационная среда деградировала — INFO

Нет project venv; глобальный Python 3.13.7 при lock 3.11+Linux (py launcher:
3.13/3.12/3.10 — 3.11 вообще не установлен); глобальный schemathesis-плагин
сломан (обходится `-p no:schemathesis`); pre-commit hook в `.git/hooks` не
установлен; `htmlcov/` стейл с апреля. CI это компенсирует, но каждая локальная
верификация начинается с обходных манёвров, а full mypy/pytest локально
невозможны в принципе. Дёшево: установить Python 3.11 + `.venv` — уйдут
env-mismatch-фейлы класса `test_api_namespace` и schemathesis-гоча.

### N7 — commercial-upgrade-plan.md стейл — INFO (carried I3)

RQ-чекбоксы не отражают выполненное (RAGAS-отчёты существуют, S1 закрыт).
Обновить или пометить superseded ссылкой на `docs/audits/`.

---

## 4. Открытый остаток (carried, гейты соблюдаются)

| ID | Что | Гейт |
|---|---|---|
| **R-2 (Q1)** | Heavy-прогон `ab_context_precision` — 8 плеч, SHIP-критерии вшиты | Mac свободен от DE-soak; one-command в `docs/operations/2026-07-18-q1-context-precision-ab-plan.md` |
| **R-3 (Q1b)** | Nightly RAGAS drift-job (Helm cron-паттерн есть) | после результатов Q1-прогона |
| **R-4 (A1)** | Multi-replica implementation (план фазовый готов) | реальный SLA, которого single-pod не тянет — сейчас его нет |
| **R-5 (C1)** | Распил `agent/graph.py` (2652) / `api/app.py` (1848) | только по явному решению владельца («no silent broad refactors») |
| **L1** | Silent `except/pass` ~65 вне тестов | точечно, при работе в соответствующих модулях |

Явные non-goals без новых данных (подтверждаю grok §16): factcard в дефолт,
авто-роутер, multi-worker без externalization, broad LangChain-рерайты.

---

## 5. Scorecard

| Dimension | 16.07 (grok) | **18.07 (fable)** | Почему |
|---|---:|---:|---|
| Code / lint / types | 9.2 | **9.2** | ruff clean, strict-scope не менялся |
| RAG design | 9.1 | **9.1** | без изменений |
| RAG proven quality | 7.4 | **7.4** | харнесс готов, но числа те же — прогон ждёт Mac |
| Security | 8.7 | **9.2** | D1 чист (перепроверено), S1+Origin-гейт+logout, bandit 0 High/0 Med |
| Architecture / complexity | 7.4 | **7.5** | +design-doc с инвентаризацией state; сами модули те же |
| Tests | 8.2 | **8.1** | T1 закрыт, но N1: покрытие 80 дней не меряется |
| Observability / ops | 9.8 | **9.8** | не трогали — правильно |
| Process / evidence | 9.3 | **9.2** | волна-2 образцовая, но N1+N2 — «спящие» гейты, P1 — незапушенный хвост |
| **Overall** | **8.9** | **≈9.0** | оценка без адверсариальной перепроверки, консервативная |

---

## 6. Вердикт

Волна-2 закрыла всё, что было закрываемо с Windows, и закрыла честно — с
адверсариальным ревью security-части и с гейтами на всё тяжёлое. Новых
код-дефектов этот проход не нашёл; нашёл **три слепых пятна процесса**:
незапушенный коммит (P1), мёртвый coverage-гейт (N1) и никогда не
срабатывающий regression-eval (N2). Все три чинятся суммарно за ~2 часа и
превращают «выглядит защищённым» в «защищено».

Продуктовый потолок прежний и хорошо известен: **context_precision 0.51** —
единственная HIGH-линия, и она упирается не в код (харнесс готов), а в
свободный Mac. Это следующий содержательный шаг проекта.

План доработок: `plan_fable_18_07_26.md`.
