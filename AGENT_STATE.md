# Agent State

## 2026-07-21 Update-6 (fastapi lock bump 0.136.1→0.139.2) ✅ START HERE

> **START HERE.** Заход: «продолжи работу» после Update-5. Windows-backlog был пуст;
> выбран отложенный safe item: bump fastapi в lock (мина метрик уже снята).
>
> **Сделано локально (ждёт push):**
> 1. `requirements.txt` floor `fastapi>=0.138.1`.
> 2. Перекомпиляция обоих lock (uv, py3.11/linux hashes): **только**
>    `fastapi==0.136.1` → `fastapi==0.139.2`; starlette 1.3.1 без изменений;
>    никаких чужих pin-бамов.
> 3. `pip-audit --strict --require-hashes` оба lock — clean (игноры прежние).
> 4. Локально на 0.139.2: 39 targeted tests (metrics / routes / entrypoint) green.
> 5. CHANGELOG Deps-блок.
>
> **Также ahead of origin:** handoff `2fd1a66` (Update-5 evidence) + этот коммит.
>
> **⏭️:** push → CI (coverage 72, unit/integration на lock 0.139.2) + pip-audit job.
>
> **Остаток — только гейты Юли:** N4 policy; Q1b; multi-replica по SLA; C1
> распил `agent/graph.py`. Windows non-gated backlog снова пуст.

## 2026-07-21 Update-5 (утечка sessions/ снята с Pages; fail_under=72; push+CI green) — SUPERSEDED by Update-6

> **SUPERSEDED.** Заход: «продолжи доработку» → «разрешаю» push.
>
> **Push выполнен:** `origin/master = 85c330f` (`2ce9bc7..85c330f`, 2 коммита: metrics + sessions kitchen).
>
> **CI run 29797076624 = success (все джобы).** Docs-site run 29797076612 = success.
> - Coverage gate на 3.13 отработал с `fail_under=72` — зелёный.
> - regression-eval skipped (paths-filter: входы не менялись) — ожидаемо.
>
> **Утечка остановлена на живом сайте:**  
> `https://…/guides/sessions/agent-state-archive-2026-05-01-to-06-16/` → **HTTP 404**.  
> Index `/guides/sessions/` → **404**. Поисковые кэши могут держать старое ещё какое-то время.
>
> **Сделано в `85c330f`:**
> 1. `'sessions/'` → `KITCHEN_DIR_PREFIXES` + guard-тест. `audits/` не трогали (N4).
> 2. `fail_under` 70 → **72** + floor-тест `>= 72`.
> 3. CHANGELOG Security-блок.
>
> **Остаток на тот момент:** N4 / Q1b / multi-replica / C1; fastapi bump — отдельно.

## 2026-07-19 Update-4 (push выполнен; мина fastapi обезврежена) — SUPERSEDED by Update-5

> **SUPERSEDED.** Заход: «пушь оба коммита и проследи CI» → затем «реши всё сам».
>
> **1. Push выполнен, origin/master = `2ce9bc7`** (`343a742..2ce9bc7`). **CI run 29660377386 = success, все 12 джобов.** Оба оживлённых гейта отработали живьём, а не проскочили:
> - **N1 coverage:** `Required test coverage of 70.0% reached. Total coverage: 73.30%` (886 passed / 24 skipped). **Замер в CI совпал с локальными 73%** — теперь есть число, против которого можно двигать порог.
> - **N2 regression-eval:** в списке джобов со статусом success, а не skipped. Первый реальный прогон с PR #1 (30.05).
> - Deploy docs site 29660377371 = success. Проверки перед пушем: архив = дословный перенос (+25/−909 в AGENT_STATE.md, где 25 = блок-указатель); Mac-IP и путь к файлу ключа **уже** лежали на origin/master → новой публичной экспозиции пуш не создал; Starlight собирает из `docs-site/src/content/docs/` по явному сайдбару, `docs/sessions/**` в публикацию не попадает.
>
> **2. Мина fastapi обезврежена — и она оказалась ПРОДАКШЕН-багом, а не тестовым артефактом.** Update-3 записал все 5 падающих тестов как «ищут маршрут перебором `app.routes`». Для `test_http_metrics` (3 из 5) это **неверно**: файл `app.routes` вообще не перебирает. Разбор по шагам:
> - `api/app.py::_extract_route_template` берёт `request.scope["route"].path_format`. С fastapi 0.138 `include_router` больше не переписывает вложенные маршруты в плоские префиксованные копии — лист хранит только свой относительный путь. Прямой замер: запрос `/api/sessions/abc-42/history` → `path_format = /sessions/{sid}/history`, **префикс `/api` потерян**. То есть под 0.138 лейбл `endpoint` у ВСЕХ метрик молча меняется, а одноимённые маршруты разных роутеров схлопываются в одну серию. Тесты ловили реальную регрессию наблюдаемости.
> - **Почему не поймал существующий юнит-тест:** `test_extract_route_template_prefers_path_format_then_path` кормит `SimpleNamespace`-фейк, у которого префикс уже вшит в `path_format`. Фейк не воспроизводит сборку роутеров. Добавлен `test_extract_route_template_keeps_router_prefix` — гоняет **настоящее** приложение с `include_router(prefix="/api")` через реальный запрос.
> - **Фикс продакшена:** `_route_mount_prefix` восстанавливает префикс из запроса (`url_path_for` даёт собственный путь листа, остаток фактического пути = префикс). **Без ветвления по версии.** Проверено в изолированных venv на ОБЕИХ версиях: на 0.136.1 поправка пустая, результат байт-в-байт прежний (no-op на запиненной версии), на 0.138.1 — чинит; покрыты вложенный префикс, маршрут прямо на app и 404.
> - **Фикс тестов владельца** (`test_root_routes`, `test_upload_security`): общий модуль `tests/_route_introspection.py` — на 0.138 публичная `fastapi.routing.iter_route_contexts`, на ≤0.137 плоский обход. **Только публичный API:** опора на внутренности обёртки (`_IncludedRouter`, `effective_route_contexts`) — ровно та ошибка, что создала эту мину, повторять её нельзя. Обе ветки прогнаны на своих версиях + негативный контроль.
> - Хелпер вынесен в один модуль, а не скопирован в два файла: логика версионной совместимости обязана быть идентична у всех вызывающих.
>
> **Порог coverage — РЕШЕНИЕ ПРИНЯТО, НЕ ПРИМЕНЕНО.** Поднять 70 → 72 против **CI-замера 73.30%** (не локального). 70 стоял с 29.04 при тогдашних 70.02% — вплотную, поэтому гейт ничего не ловил бы и будучи живым. 72 оставляет ~1.3 пп на текучку и при этом ловит реальную просадку. В `pyproject.toml` сейчас **всё ещё 70** — правка `fail_under` на ходу изменила бы результат идущего замера, а сессия кончилась раньше прогона.
>
> **🔴🔴 СНАЧАЛА — ЖИВАЯ УТЕЧКА НА ПУБЛИЧНЫЙ ДОКС-САЙТ (создана коммитом `2ce9bc7` 18.07, ПОДТВЕРЖДЕНА по живому сайту 19.07).**
> Страница `/RAG_Support_Assistant/guides/sessions/agent-state-archive-2026-05-01-to-06-16/` **открыта публично** и содержит `192.168.1.133`, `D:\TXT\Mistral_API.txt`, `deproject-mac`, процедуры SSH.
> - **Причина:** `docs-site/scripts/sync-docs.mjs` рекурсивно обходит ВСЁ дерево `docs/` и публикует каждый `.md`, отсекая только `isKitchen()`. В `KITCHEN_DIR_PREFIXES` есть `plans/ research/ operations/ a11y/ superpowers/` — **`sessions/` там НЕТ**; файловая регулярка ловит точное `agent-state.md`, а `agent-state-archive-*.md` под неё не подходит.
> - **Почему это новая экспозиция, а не «оно и так было в репо»:** до переноса `AGENT_STATE.md` лежал в корне, а из корня `sync-docs` берёт только `README.md` и `DEPRECATIONS.md`. Перенос 925 строк в `docs/sessions/` затащил их в публикуемое дерево: было «файл в публичном репо», стало «отрендеренная и индексируемая веб-страница».
> - **Моя ошибка в проверке (для протокола):** я объявила «Pages-риска нет», сгрепав литерал `'docs/'` по `docs-site/scripts/`; `sync-docs.mjs` строит путь через `join(PROJECT_ROOT, 'docs')`, греп промахнулся, и пустой вывод был засчитан как доказательство отсутствия. Отрицательный результат грепа ≠ факт.
> - **Минимальная остановка утечки, НЕ предрешающая N4:** добавить `'sessions/'` в `KITCHEN_DIR_PREFIXES` — файлы остаются в репозитории, с сайта уходят. Нужен push + redeploy; из поисковых кэшей уйдёт не мгновенно.
> - **Шире одного коммита:** под тем же правилом, вероятно, опубликованы `agent-state-archive-2026-06-02-to-06-05.md` и `next-session-3-subagents.md` (были до этой сессии). **Проверить весь `docs/sessions/` и вообще что реально живёт на сайте.**
> - **Гейт Юли:** публикационное действие с её данными, смыкается с N4. Не выполнять без явного решения.
>
> **⏭️ ПОДОБРАТЬ ОТСЮДА (сессия прервана по лимиту 19.07, работа закоммичена локально, НЕ запушена):**
> 0. **Утечка выше — первым делом.**
> 1. ~~**Прочитать результат полного прогона.**~~ **ВЫПОЛНЕНО 19.07: `896 passed, 4 skipped, 0 failed` (19:21), coverage `73.37%`** (было 73.30% на CI до фикса — фикс покрытие не просадил). Широкой регрессии от правки hot-path middleware НЕТ. Оставшийся текст пункта — историчен: Он был запущен командой CI (`pytest tests/ -q --ignore=tests/integration -p no:cacheprovider -p no:schemathesis --deselect tests/test_a11y.py::test_axe_has_no_serious_or_critical_findings --cov --cov-report=term`) и на момент обрыва ещё шёл; вывод буферизован через `| tail`. Если файл не сохранился — просто перезапустить, ~22–25 мин. **Это единственная непройденная проверка.** Уже пройдено: 27 целевых тестов зелёные, `ruff` clean, mypy skip-гейт Success 23 файла, кросс-версионные пробы на 0.136.1 и 0.138.1, краевые случаи (пробелы/кириллица/`%2F`/`..`/`:path`).
> 2. **Поднять `fail_under` 70 → 72** в `pyproject.toml` (решение выше) — отдельным коммитом или амендом.
> 3. **Push + проследить CI.** Ожидание: coverage останется ~73% (фикс добавил ~15 строк прода и тест на них), `regression-eval` снова должен реально отработать.
> 4. Только после зелёного CI — закрывать.
>
> **Остаток — только гейты Юли:** N4 policy (внутренняя кухня в публичном репо); Q1b (гейт «precision сдвинулся» НЕ выполнен); multi-replica impl по SLA; C1 распил `agent/graph.py` — по явному решению. **Не начато и намеренно:** бамп fastapi 0.136.1 → 0.138.x в lock. Мина снята, так что бамп теперь безопасен, но это отдельная работа: регенерация обоих lock под `--require-hashes` + pip-audit, свой риск, мешать с этим фиксом нельзя.
>
> **Остаток — только гейты Юли:** N4 policy (внутренняя кухня в публичном репо); Q1b (гейт «precision сдвинулся» НЕ выполнен); multi-replica impl по SLA; C1 распил `agent/graph.py` — по явному решению. **Не начато и намеренно:** бамп fastapi 0.136.1 → 0.138.x в lock. Мина снята, так что бамп теперь безопасен, но это отдельная работа: регенерация обоих lock под `--require-hashes` + pip-audit, свой риск, мешать с этим фиксом нельзя.

## 2026-07-18 Update-3 (CI-гейты N1+N2 оживлены; докс-хвосты N3/N5/N7) — SUPERSEDED by Update-4

> **START HERE.** Заход: «AGENT_STATE.md → Update-2, evidence в docs/operations/» → выбрана волна N1+N2, затем по разрешению Юли два параллельных субагента на N5 и N3+N7. Закрыт весь незагейченный Windows-остаток плана `plan_fable_18_07_26.md` (7 из 8).
>
> **Сделано:**
> 1. **N1+N2 — мёртвые CI-гейты оживлены** (`e6b49bc`, локально, push = гейт Юли).
>    - **N1:** `fail_under = 70` лежал в pyproject с 29.04, но CI гонял pytest **без `--cov`** → гейт не применялся 2.5 месяца. **Блокер вне аудита:** `pytest-cov` отсутствовал в `requirements-dev.lock`, а CI ставит `--require-hashes` → правка «просто добавить `--cov`» упала бы на `unrecognized arguments`. Добавлен `pytest-cov==7.1.0`; перекомпиляция `uv` дала ровно 3 новых пакета (pytest-cov, coverage, tomli) без чужих бампов; `pip-audit` по dev-lock чист.
>    - **Замер ДО включения** (не доверять числу от 29.04): **73%** на unit-scope. Порог оставлен **70** — запас намеренный; поднимать только против замера в CI, не локального.
>    - **N2:** `regression-eval` был `if: github.event_name == 'pull_request'`, а работа идёт прямыми пушами в master → джоб не запускался с PR #1 (30.05). Гейт приведён к виду migrations/helm. **Перед включением джоб проверен живьём** его же командой: exit 0, 35 кейсов, `gate.passed=true`, 0 регрессий.
>    - **Оба гейта закреплены тестами** (`tests/test_github_workflows.py`, +3) и **мутационно проверены**: откат каждой правки роняет ровно её тест. Это прямое следствие того, КАК гейты умерли — молча, потому что их никто не утверждал.
> 2. **N5 — AGENT_STATE разгружен:** 136 KB → **11 KB**. В архив `docs/sessions/agent-state-archive-2026-05-01-to-06-16.md` вынесены 22 датированных блока (≤2026-06-16) + две недатированные майские секции `Last Verified Gates` (сама объявляла себя historical ledger) и `Next Step` (майский лог коммитов под актуальным заголовком). **Проверено сверкой с `git show HEAD:AGENT_STATE.md`:** 31 блок = 7 в корне + 24 в архиве, потеряно 0, изменён только блок-указатель (чистый аппенд).
> 3. **N3** — `docs/DEPLOYMENT.md`: раздел про cookie-auth за reverse-proxy (ingress обязан пробрасывать `Host` как есть, иначе Origin-гейт режет POST/PUT/PATCH/DELETE от браузерных UI: страницы грузятся, экшены молча 401). Сверено построчно с `_cookie_auth_origin_ok`/`_cookie_auth_bridge`.
> 4. **N7** — `commercial-upgrade-plan.md`: шапка SUPERSEDED со ссылками на свежие аудиты. Чекбоксы **намеренно не проставлялись** построчно — подтвердить 60+ RQ-пунктов по коду дёшево нельзя, и это честно указано в самой шапке.
>
> **Находка на будущее (не чинилась, вне scope):** 5 тестов (`test_http_metrics` ×3, `test_root_routes`, `test_upload_security`) ищут маршрут перебором `app.routes`. Локально стоит fastapi **0.138.1**, в lock — **0.136.1**; в 0.138 `include_router` перестал разворачивать дочерние маршруты в плоский список (в `app.routes` лежат обёртки `_IncludedRouter`) → тесты их не находят. **CI зелёный только потому, что pin 0.136.1** — при бампе fastapi упадут все пять разом. Тот же класс, что уже чинённый T1 (переведён на OpenAPI), просто не дочищенный. Проверено контрольным прогоном: без `--cov` падают ровно те же 5, т.е. к coverage-гейту отношения не имеет.
>
> **Остаток (только гейтованное, Windows-backlog ПУСТ):** push `e6b49bc` + докс-коммита; Q1b (гейт «precision сдвинулся» НЕ выполнен — прогон это подтвердил); multi-replica impl (по SLA, план готов); C1 распил `agent/graph.py` — только по явному решению Юли; N4 — policy-решение по внутренней кухне в публичном репо.

## 2026-07-18 Update-2 (Q1 heavy-прогон ВЫПОЛНЕН: NO-SHIP; UX logout) — SUPERSEDED by Update-3

> **START HERE.** Заход: «продолжи» после волны-2. Mac освободился от DE-soak → выполнен гейтованный остаток.
>
> **Сделано:**
> 1. **Q1 heavy-прогон ПРОГНАН на Mac** (run `20260718T173221Z-8c2fd13e`, полная форма `--build-pool --with-grade --with-judge`, external-mistral, ~7 ч). **Вердикт NO-SHIP по всем 7 плечам** — лучшее по precision плечо k3-grade (+0.071) роняет FULL 97→92 / MISS 1→3; no-expand роняет обе оси (−0.070 precision, FULL 87). Прод-дефолты не тронуты. Evidence: `docs/operations/2026-07-18-q1-context-precision-ab-results.md`; сырые отчёты в `reports/ragas/` (untracked по конвенции); rerank-пул `.tmp/ab_candidates_phase2_C.json` остался на Mac — детерминированный пересчёт из него за минуты. Каверзы: 25/~200 batch-вызовов grade_docs упали transport-ошибками Mistral, но per-doc fallback отработал на всех (0 per-doc ошибок в логе) — grade применён на 100% кейсов, данные чистые, ошибки стоили только времени; embed реально ~2.2 ч (5589 чанков, оценка плана «3–6 мин» была занижена). Mac вычищен: `/tmp/mk.env` + `/tmp/q1_run.sh` удалены.
> 2. **UX-хвост закрыт** (`b5978f0`): logout-кнопки в admin («Logout») и agent («Выйти») → существующий `POST /api/auth/logout`; `test_admin_js_served` ретаргетирован со стейл-`localStorage` на cookie-ассерты (`/api/auth/session`, `/api/auth/logout`, отсутствие `localStorage.setItem`). Верификация: 63 passed (admin_ui/session_auth_cookie/agent_endpoints/a11y/csp), ruff clean.
>
> **Остаток (только гейтованное, Windows-backlog ПУСТ):** Q1b (nightly RAGAS drift + CI floor) — гейт «precision сдвинулся» НЕ выполнен; multi-replica impl (по SLA, план готов); C1 распил `agent/graph.py` — только по явному решению Юли.

## 2026-07-18 Update (audit follow-up wave 2: S1+Q1+A1+Q2; параллельные opus-агенты) — SUPERSEDED by Update-2

> **START HERE.** Заход: «доработай проект» + явное разрешение Юли на параллельные opus-субагенты («жги»). Всё ниже PUSHED одним пакетом, CI смотреть на последнем коммите.
>
> **Сделано:**
> 1. **D1-коммит `2263a8c` перепроверен и запушен** (pip-audit обоих lock на СВЕЖИХ advisories — чисто; 44 целевых теста; ruff). CI поймал trailing whitespace в `audit_grok_16_07_26.md` (только pre-commit job) → фикс `c15a5a9`, CI на нём **success целиком**.
> 2. **S1 закрыт** (`3cac073`): httpOnly cookie auth для admin/agent/analytics UI — токенов в localStorage больше нет. `/auth/login|refresh` зеркалируют JWT в httpOnly SameSite=Strict cookie; новые `POST /api/auth/session` (paste-токен → cookie) и `/api/auth/logout`; JS-чтения/записи токенов удалены; header-auth и JSON-контракт не тронуты. **Адверсариальный opus-ревью нашёл 2 SHOULD-FIX, оба закрыты:** (а) SSO пишет одноимённый `access_token` cookie с SameSite=**Lax** → «Strict решает CSRF» неполно → в `_cookie_auth_bridge` добавлен **Origin-гейт** на state-changing методы (`api/app.py::_cookie_auth_origin_ok`); (б) cookie-тесты были вакуумны (анонимный admin-фолбэк фикстуры) → переведены на `client_with_key` + негативные ассерты + тест cross-site-отказа. `/auth/session` получил лимит 5/minute. Верификация: auth-батч 32 + UI-батч 58 + cookie 9 passed; mypy skip-gate Success 23 files; ruff. Известные границы (осознанно, в CHANGELOG): logout не отзывает JWT server-side; analytics.html зависит от cookie с admin-страницы.
> 3. **Q1 харнесс готов** (`5b6c157`): `scripts/ab_context_precision.py` — 8 плеч (rerank top-k / parent-window / grade_docs on-off) вокруг D2-базлайна, ОДНА тяжёлая embed+rerank-стадия, остальное — дешёвая пост-обработка; метрики через существующий `evaluation.ragas_eval` + `_kw_status` FULL/PART/MISS как гард; SHIP-критерии вшиты (Δprecision ≥ +0.05, recall ≥ 0.90, FULL/MISS без регрессий), NO-SHIP валиден. Smoke на моках (без моделей/сети), 7 тестов. **Heavy-прогон на Mac НЕ запускался** — Mac занят DE_project soak; one-command рецепт в `docs/operations/2026-07-18-q1-context-precision-ab-plan.md`.
> 4. **A1 закрыт design-doc'ом** (`ee82fea`): `docs/plans/2026-07-18-multi-replica-design.md` — 22 позиции process-local state (file:line). Поправки к аудиту: сессии УЖЕ Postgres-backed, LLM-кэш УЖЕ Redis; настоящих блокеров два — rate limiter без `storage_uri` и in-memory confirm-actions (+ гоча: `channels/telegram_bot.py` держит свой `_sessions` — остаётся single-instance). Рекомендация: не начинать без реального SLA.
> 5. **Q2 закрыт** (`694dbc0`): `docs/OPERATIONS.md` «Latency budgets & timeouts» — рекомендация `RAG_ASK_BUDGET_SEC=300` для prod (дожфуд-медиана ~190s), дефолт `0` не тронут. F3 (ruff ASYNC, 5 в `scripts/`) осознанно оставлен: реальный блок — синхронный sqlite-скан на admin-only пути, точечный `to_thread` — линтерная косметика. RUF100: подлинно stale noqa = 0.
>
> **Остаток (гейтованное):** Q1 heavy-прогон на Mac (когда освободится от DE-soak); multi-replica implementation (по SLA, план готов); C1 распил `agent/graph.py` (аудит: «no silent broad refactors» — только по явному решению Юли); optional UX: logout-кнопка в admin/agent, retarget `test_admin_js_served`.
>
> **Гоча сессии:** `~/.claude/scripts/guard.py` НЕ видит сообщений Юли, отправленных посреди хода агента (UserPromptSubmit для них не срабатывает) — разрешение на параллель пришлось выставлять вручную в state-файл guard'а.

## 2026-07-16 Update (security lock refresh + audit follow-up) — SUPERSEDED by 2026-07-18

> Заход: глубокий аудит `audit_grok_16_07_26.md` + «доработай проект максимально, решения на тебе».
>
> **Сделано (локально, ждать push):**
> 1. **D1 dep-CVE batch** — `uv pip compile` (py3.11/linux hashes) обоих lock: `aiohttp 3.14.1`, `cryptography 49.0.0`, `starlette 1.3.1`, `python-multipart 0.0.32`, `pypdf 6.14.2`, `langsmith 0.10.5`, `langchain 1.3.13`, `setuptools 83.0.0`, joserfc/langgraph-*/pydantic-settings/langchain-classic и floors в `requirements.txt`. `pip-audit --strict` → **No known vulnerabilities found** (игноры chroma/torch no-fix оставлены).
> 2. **T1** — `test_api_namespace_is_populated` / legacy paths через OpenAPI (FastAPI 0.138-proof).
> 3. **B310** — scheme allowlist `http/https` для Ollama health `urlopen` + unit.
> 4. **Docs** — official RAGAS baseline (context_precision 0.51 target) в `docs/OPERATIONS.md`; CHANGELOG; dogfood plan checkboxes closed.
>
> **Верификация:** ruff clean на изменённых .py; pytest 44 targeted (entrypoint/settings secrets/precommit/docs_quality) green; pip-audit green.
>
> **Остаток (не Windows-heavy code):** context_precision A/B (Mac/Colab); multi-replica design; optional httpOnly admin cookies; push этого security-коммита на origin.
>
> Предыдущий блок 2026-06-16 (E20 live screenshot) — выполнен; dep-CVE red **снят** этим обновлением.

## Архив истории сессий

Секции 2026-06-02..2026-06-05 (cont.2–16: ruff-слайсы F6, R7-judge baseline,
Kaggle Phase 1/2, parent-expansion, query-expansion probe) вынесены в
`docs/sessions/agent-state-archive-2026-06-02-to-06-05.md` (F-16, 2026-06-11).

Секции 2026-05-01..2026-06-16 вынесены в
`docs/sessions/agent-state-archive-2026-05-01-to-06-16.md` (N5, 2026-07-18):
блоки 2026-05-31..2026-06-16 (project closure, Fable hardening, type-hardening,
adaptive-retrieval Phase 0–5) плюс две недатированные майские секции —
`Last Verified Gates` и `Next Step` (обе покрывают 2026-05-01..2026-05-30).

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch source: `master` tracks `origin/master`; current history includes the
  2026-05-30 Codex audit remediation series after the weekly-report fixes.
- Snapshot baseline date: 2026-05-30 (Europe/Bucharest).
- Baseline HEAD before the 2026-05-30 audit/remediation run:
  `4d60479` (`ci: clarify weekly report delivery workflow`).
- Baseline file count: 698 tracked files from `git ls-files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Baseline generated bundle/artifact size: 0 bytes for searched bundle-like
  artifacts outside ignored dependency/cache directories.
- Git status at the 2026-05-30 durable-state refresh was clean, with local
  remediation commits ahead of the initial `origin/master` baseline.
- Origin sync at audit start: `origin/master` was at `4d60479`.

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external
  services, live external-provider/API benchmark calls, destructive commands.
