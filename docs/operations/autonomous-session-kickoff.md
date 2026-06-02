# Autonomous session kickoff — RAG Support Assistant

Назначение: запустить новую сессию, которая работает **без перерыва и сама принимает решения**.
Прочитай этот файл первым, выполни «Первые 5 минут», затем бери верхний незаблокированный
пункт из §4 и веди его до измеримого результата. Не возвращайся с меню — решай и делай.

---

## ⭐ RESUME (2026-06-02) — R1 ЗАШИПЛЕН, full-corpus A/B идёт на Mac

**R1 закрыт в коде и запушен** (master `9b219fa` = origin/master, CI зелёный): дефолт reranker → `BAAI/bge-reranker-v2-m3` (`90891e5`); push поймал свежий pyjwt CVE → bump `2.13.0` (`9b219fa`). Бэклог §4 пункт 1 (reranker fix) — **DONE**. Гоча на будущее: CI `pip-audit` = PyPI advisory service (не osv); osv-only `authlib`/`langchain-classic` CVE CI не валят (отложены осознанно).

**Сейчас на Mac (8GB Intel) считается full-corpus reranker A/B** — финальная валидация дефолта на всех 201 docs (не на 10-FAQ-подвыборке). Запущено detached+nohup, переживает закрытие управляющей сессии:
- Phase A (PID 96542): ingest 201 docs (~7000 чанков, bge-m3 CPU) + RRF-кандидаты по 100 кейсам → `/tmp/ab_candidates.json`.
- Chainer (PID 97247): ждёт Phase A → Phase B (3 руки **OFF / ms-marco / bge-v2-m3**, keyword-coverage @ top-5) → пишет результат в **`~/RAG_Support_Assistant/.tmp/ab_result_20260602.txt`**.
- Скрипты: `.tmp/ab_twophase.py` (3-arm), `.tmp/ab_chain.sh`. Корпус залит (201), Mac-репо на `9b219fa`, все 3 модели в HF-кэше.

**Подобрать результат в новой сессии:**
```bash
ssh julia@192.168.1.133 "grep -c '\[chain\] DONE' /tmp/abB.log; tail -40 ~/RAG_Support_Assistant/.tmp/ab_result_20260602.txt"
```
DONE есть → написать отчёт `docs/operations/2026-06-02-mac-fullcorpus-reranker-ab.md` (числа OFF/ms-marco/bge-v2-m3) + сверить с 10-FAQ-baseline (OFF 100% / ms-marco 61% / bge 100%) → вывод: подтверждает ли full-corpus дефолт bge-v2-m3. Дефолт обратим через `RAG_RERANKER_MODEL`, так что сюрприз = отдельное решение, не блокер. Если Mac уснул/ребутнулся и результата нет — перезапустить `nohup ... .tmp/ab_twophase.py a` затем `b` (рецепт §6).

---

## 1. Миссия и проверенное состояние (на 2026-05-30)

Продукт: универсальный гибкий RAG-ассистент поддержки (FastAPI + LangGraph + Chroma + BGE-M3).
Цель текущей линии работ: довести RAG-качество от «архитектурно SOTA, но неизмеренного» до
**измеренного и настроенного под RU**, опираясь на `audit_claude_30_05_26.md` (findings R1–R7).

Уже сделано и **верифицировано на железе** (не гипотезы):
- Демо-корпус: 201 RU-док в `data/uploads/aircargo/` (тенант `aircargo`; `data/*` gitignored).
  Медиана дока ~21 200 символов, структурированный markdown.
- R7-стартовый eval: `evaluation/curated_cases_aircargo.jsonl` (31 RU-кейс, guard-тест зелёный).
- **R1 ДОКАЗАН на iMac**: retrieval top-5 keyword-coverage — реранкер OFF **100%** vs дефолтный
  англ. `ms-marco-MiniLM` **61%** (Δ−39пп). Англ. реранкер на RU активно вредит. Отчёт:
  `docs/operations/2026-05-30-mac-rag-retrieval-baseline.md`.
- **R2 подтверждён живьём**: `Contextual header exceeded chunk_size; truncating chunk`.
- ADR GraphRAG (defer-with-seam): `docs/adr/0001-graphrag-deferral-and-trigger.md`.
- План: `docs/plans/2026-05-30-demo-corpus-and-rag-grounding.md` (§7 = порядок по ROI).

Эти артефакты **не закоммичены** (untracked + 1 modified test) — push только по явной просьбе.

---

## 2. Контракт автономии (что решаю сам, где стоп)

**Решаю и делаю сам, без вопросов:**
- Какой пункт §4 брать следующим и как его выполнить.
- Любые локальные правки кода/доков/тестов, прогон лёгких тестов, ruff.
- Прогоны на iMac/Colab (ingest, eval, A/B) — это и есть основная работа.
- Выбор технических средств (uv, pin версий, mirror, env-флаги).
- Диагностика и фикс поломок среды (как ML-пин и hf-xet ниже).

**Останавливаюсь и спрашиваю ТОЛЬКО при (реальный gate):**
- `git push` / публикация наружу / деплой / удаление невосстановимого.
- Трата платной квоты с риском (массовые live-LLM прогоны на платном ключе — оценить объём).
- Отсутствует доступ/креденшл, которого нет в проекте/`D:\TXT\`/DE_project.
- Решение, меняющее продукт необратимо без возможности отката.

**НЕ останавливаюсь** на: «делать ли вообще», выбор A/B/C реализации, «продолжать ли» —
это всё решаю сам. «работай автономно» = доводить до конца, а не возвращаться со списком опций.

Источник правил: `~/.claude/CLAUDE.md` + памяти `feedback_autonomy_no_offer_lists`,
`feedback_autonomous_means_finish`, `feedback_unblock_with_tools_not_menus`, `feedback_vse_means_all_not_stop`.

---

## 3. Карта среды и где что делать

| Среда | Роль | Ограничение |
|---|---|---|
| **Windows (D:\, эта машина)** | thin client: код, лёгкие тесты, доки, staging, orchestration по SSH | **НЕЛЬЗЯ процессы > ~1 ГБ RAM**: ни ingest, ни BGE-M3, ни Docker, ни RAGAS. Память: `feedback_weak_machine_offload_heavy` |
| **iMac `julia@192.168.1.133`** | heavy-offload: ingest/eval/смоук | 8 ГБ Intel — малые подвыборки OK; полный корпус 7K чанков / 2-я большая модель → нет. Детали: память `reference_imac_offload_host` |
| **Colab** | самое тяжёлое: полный корпус, bge-reranker-v2-m3, RAGAS, GraphRAG-индекс | GPU бесплатно; on-demand MCP (`reference_colab_mcp_optional`). Корпус gitignored → доставить отдельно |

Что можно прямо на Windows (см. план §6): код-шов query routing, markdown-structural splitter
(чистая функция + мок-тесты), расширение curated-кейсов (текст), доки.

---

## 4. Бэклог по приоритету (бери верхний незаблокированный, веди до результата)

1. **Закрыть R1 на iMac** (готово к запуску, средство есть): тот же A/B, но третья рука —
   `RAG_RERANKER_MODEL=BAAI/bge-reranker-v2-m3`. Цель: показать, что мультиязычный реранкер
   восстанавливает coverage к ~100% (закрытие R1, не «выключить»). ВНИМАНИЕ 8 ГБ: BGE-M3 (2.3ГБ)
   + bge-reranker-v2-m3 (2.3ГБ) одновременно = риск OOM; если упрётся — гнать на Colab, либо
   ретрив-кандидаты один раз, затем скорить рерранкерами по очереди с выгрузкой.
2. **chunk-size / structural** (локально код, eval на iMac/Colab): реализовать
   markdown-structural splitter как opt-in флаг `RAG_STRUCTURAL_CHUNKING` (план §3.1, карта 3
   сайтов чанкинга там же), юнит-тест локально; A/B на корпусе — на iMac.
3. **R5 — BGE-M3 native sparse** вместо `.split()` BM25 (план §3.3): модель уже загружена.
4. **query routing** через `classify_complexity` (план §3.5): локально код+мок-тесты, eval на iMac.
5. **R7 расширение** 31→100–150 кейсов + RAGAS+Mistral (Colab; ключ Mistral в `.env`/`D:\TXT\`).
6. **GraphRAG-шов** `RAG_RETRIEVAL_STRATEGY` (ADR 0001) — код локально, включение при trigger.

Каждый пункт: сначала измерь baseline, потом дельту; не «вкатывай вслепую». Результат каждого —
число + запись в `docs/operations/` или README.

---

## 5. Первые 5 минут новой сессии (bootstrap)

```powershell
# 1. Онбординг проекта (правило CLAUDE.md): прочитать свежие .md
#    AGENT_STATE.md, BACKLOG.md, audit_claude_30_05_26.md,
#    docs/plans/2026-05-30-demo-corpus-and-rag-grounding.md, этот файл.
# 2. Состояние гита (push НЕ делать без спроса)
git -C D:\RAG_Support_Assistant status --short --branch
# 3. Проверить связь с iMac (heavy-offload)
ssh -o BatchMode=yes -o ConnectTimeout=10 julia@192.168.1.133 "echo OK; sw_vers -productVersion"
# 4. Проверить, что прошлая среда на iMac жива
ssh -o BatchMode=yes julia@192.168.1.133 "cd ~/RAG_Support_Assistant && .venv/bin/python -c 'import torch,sentence_transformers;print(torch.__version__)'; du -sh ~/.cache/huggingface"
```
Если `.venv`/модели на iMac живы — можно сразу гнать §4.1. Если среды нет — пересобрать по §6.

---

## 6. Рецепт heavy-прогона на iMac (с уже известными граблями)

Все грабли этой линии уже пойманы — не наступать заново (память `reference_imac_offload_host`):

```bash
ssh julia@192.168.1.133
cd ~/RAG_Support_Assistant
# venv (если нет): uv (~/bin/uv, распаковать из ~/uv.tar.gz) → uv venv --python 3.11 .venv
# ML-стек: requirements.txt, ЗАТЕМ обязательный pin под Intel-Mac:
~/bin/uv pip install --python .venv/bin/python -r requirements.txt
~/bin/uv pip install --python .venv/bin/python "numpy<2" "torch==2.2.2" "transformers==4.44.2" "sentence-transformers==2.7.0" "huggingface-hub<0.26"
~/bin/uv pip uninstall --python .venv/bin/python hf-xet     # ИНАЧЕ HF xet-CDN душит загрузку (~16KB/s)
# Запуск ВСЕГДА detached + лог (stdout буферизуется → python -u):
nohup bash -c 'HF_HUB_OFFLINE=1 RAG_SEMANTIC_CHUNKING=false .venv/bin/python -u <script>.py' > /tmp/run.log 2>&1 &
```

Правила оркестрации по SSH:
- Тяжёлый процесс — только `nohup ... &` detached (переживает обрыв ssh); поллить `/tmp/*.log`.
- Ждать результат: одна ssh-сессия **>8–9 мин падает на exit 255** (ServerAlive не спасает).
  Бить ожидание на куски ≤8 мин **или** `run_in_background: true` у Bash-тула.
- Скрипты/данные на Mac доставлять `scp` (корпус gitignored → клон его не тянет).
- Скоуп под 8 ГБ: для retrieval-проверки достаточно подмножества (10 FAQ покрывают все 31 кейса).
- `python -u` иначе вывод не виден до конца процесса.

Скрипт retrieval-проверки лежит на Mac: `~/RAG_Support_Assistant/mac_retrieval_eval.py`
(копия в `.tmp/mac_retrieval_eval.py` на Windows). Запуски: см. отчёт baseline §«Воспроизведение».

---

## 7. Антипаттерны (не повторять то, что уже разрулено)
- Не ставить ML-стек «как есть» на Intel-Mac (numpy2/torch ABI + битый transformers 5.9) — пинить.
- Не качать модели через xet — снести `hf-xet`.
- Не запускать heavy на Windows (RAM-лимит) и не обещать «live» без реального прогона.
- Не реализовывать chunking-изменения дефолтного пути до того, как снят baseline (вкатывание вслепую).
- Не пушить/деплоить без явной просьбы.
- Не возвращаться с меню «вариант A/B/C» — выбрать и сделать.
