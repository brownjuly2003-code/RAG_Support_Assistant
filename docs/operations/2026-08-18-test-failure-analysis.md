# Почему падали тесты — разбор и решения (2026-08-18)

**Статус:** закрывающий анализ этапа. Все факты проверены командами в этой
сессии (Windows, Python 3.13.7, master `bbce331`+).

## Выводы одной страницей

| Слой | Что падало | Настоящая причина | Решение |
|------|-----------|-------------------|---------|
| Unit-suite (pytest) | `tests/test_csp.py` — зависание/таймаут (300 с) на первом же `TestClient(app)` | Тест открывал `with TestClient(app)` напрямую (не через conftest `client`), запускал lifespan → `initialize_vector_store()` → на dev-машине существует `data/vectordb/chroma` → грузится реальный `BAAI/bge-m3` (2.3 GB с HF, >1 GB RAM). В CI `data/` отсутствует (gitignore) — там ветка не выполняется, поэтому CI зелёный, локально suite «висит». | `bbce331`: тест переведён на shared `client`-fixture (она стабит vector store, alembic, reaper). 3 passed / 0.4 с. |
| Unit-suite (pytest) | `tests/test_index_operator.py::test_rollback_manifest_without_previous_raises_unavailable` | Stale-контракт: `1aa9f19` (Update-194) сделал так, что первый publish записывает legacy-коллекцию как `previous_collection`; тест по-прежнему ожидал «нет previous» после публикации версии → код честно отвечает `IndexRollbackConflict`. Тот слайс гонял только «focused band», полный suite не запускался. | `bbce331`: тест публикует legacy-имя (единственный случай `previous=None`), проверяет `IndexManifestRollbackUnavailable`. |
| MyPy (локально) | CI-команда 1 падает на `numpy/__init__.pyi` (`type` statement, py3.12+) | Глобальный Python имеет numpy 2.5.1 vs lock 2.4.4; `python_version=3.11` в pyproject. Проблема окружения, не репо (VER-01: в retained 3.11-окружении обе команды зелёные; команда 2 зелёная и здесь: 31 sources). | Не чинить в репо. Гейт — CI/lock-окружение. |
| Ruff (локально) | `ruff check .` — 206 ошибок | Все — внутри 151 каталога `.pytest_tmp_*` (1.1 GB basetemp-мусора с копиями проекта). На tracked-файлах вне `archive-legacy` (исключён в CI) — чисто. | Каталоги удалены, `.pytest_tmp*/` в `.gitignore`. |
| Live quality gate §5 (seed 42, pre-QG, 2026-08-09) | candidate 65% vs baseline 70%, 4 регрессии | Реальные RAG-причины, каждая разобрана и закрыта локально: QG-01 vector-path без parent-expansion (`c3ae4f4`), QG-02 provider-exception → generic answer (`1304ff4`), QG-03A verify_facts `httpx.ReadError` → escalation fallback (`80c2603`), QG-03B/QG-04 header-shell chunk вместо контента (`5662ea7`, `5f8bb78`). | Закрыто кодом; live-реплей не проводился (см. ниже почему). |
| Live quality gate §5 (seed 42, post-QG, 2026-08-12) | candidate 25% vs baseline 90%, 13 регрессий | **Не RAG-регрессия.** Кандидат `gracekelly-mixed` (browser-scraping провайдер) вернул browser-артефакты в 18/20 ответов (12 timestamp-only, 6 prompt echo) + 2 failed-escalation; латентность 304 с/кейс vs 82 с baseline. Contained в `63aa5df` (reject `invalid_response`) + `dbd2b28` (fail-closed human/not_verified). | `gracekelly-mixed` признан непригодным как §5-кандидат. Больше платных/live seed'ов локально не тратить. |
| Live gate — инфраструктура | 20 infra-failures (`vector store is not initialized`); OOM-kill hybrid | Рабочий Windows-индекс был 6 док × **3-dim** (toy) при remote `mistral-embed` 1024; production reranker грузит 2–4 GB (>1 GB watchdog). | Guard `d157b31` (dim mismatch → fail-closed без provider-вызова); INDEX-DIM активация 3×1024 — см. Update-209. Hybrid+reranker на Windows не запускать; путь — Mac/Kaggle. |
| INDEX-DIM «lock-гейт» (Updates 199–208, 10 сессий) | `TenantIndexLockUnavailable / connection_refused` из Windows к WSL PostgreSQL | **WSL2 idle-shutdown**: инстанс гаснет через десятки секунд после выхода `wsl.exe`, унося postgres. `Test-NetConnection` True сразу после старта → через минуту refused. Не firewall/relay/DSN. | Keepalive-процесс `wsl -d Ubuntu-22.04 -u root -e sh -c 'service postgresql start; exec sleep infinity'` → lock probe зелёный (`first_acquired=true, second_acquired_while_held=false, released=true, reacquired=true`). |

## Что это говорит о процессе (и что меняем)

1. **Focused bands ≠ suite.** Три из четырёх «stale test» закрытий последних
   недель (VER-05/06/07, WS-05, теперь index_operator) — следствие правки
   контракта с прогоном узкой band. Правило: любой коммит, меняющий контракт
   в `vectordb/`, `agent/`, `api/` — полный unit-suite до коммита
   (5–6 мин на этой машине с `RAG_RERANKER_MODEL=""`).
2. **Unit-тесты не должны зависеть от локальных данных.** `data/` в gitignore
   означает, что CI и dev видят разное поведение lifespan. `client`-fixture —
   единственный допустимый способ поднимать app в тестах.
3. **Гейт должен диагностироваться за один шаг.** 10 updates на lock-гейт при
   причине «WSL заснул» — цена запрета «не трогать DSN/WSL/restart» без
   гипотезы. Диагностика конфигурации dev-машины не требует owner-authorization
   на каждое `Test-NetConnection`.
4. **§5 live-гейт в локальной vector-only/6-doc конфигурации недостижим по
   построению** (precision 0.15–0.30 vs порог 0.63; recall 0.65–0.73 vs 0.97).
   Пороги были сняты с D2 (hybrid + reranker + parent-expansion, полный корпус,
   Kaggle). Честный статус §5 — OPEN; путь к закрытию — off-Windows прогон
   полного пайплайна, не ещё один платный seed на Windows.

## Ссылки на evidence

- Suite: `.pytest_tmp_cc_20260818/full_run{,2,3}.log` (локально, ignored);
  итог зафиксирован в Update-209 `AGENT_STATE.md`.
- Live gate: `reports/regression/20260809T172531Z-*.json` (pre-QG),
  `20260812T093713Z-6121aab5` (post-QG), разбор в
  `docs/SESSION_HANDOFF.md` §1B/§1C.
- Lock probe / активация: `.tmp/index-dim-windows-activation-result-20260818.json`.
