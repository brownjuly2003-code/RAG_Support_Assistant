# Adaptive Retrieval — Phase 0: разметка + baseline + гейт

- Дата: 2026-06-13.
- План: `docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md` (workstream
  «Adaptive Retrieval Router + Fact-Card (SFR)»).
- Research: `research_adaptive.md`.
- Scope этой сессии: **только Phase 0** (T0.1 разметка + T0.2 baseline + ГЕЙТ).
  Безопасно, обратимо, офлайн на Windows — нового индекса не создаёт, eval-данные
  только читаются. Phase 1+/Track F/Track R — **за гейтом, отдельной сессией.**

## T0.1 — разметка eval-кейсов

Размечены все **135** curated-кейсов (`curated_cases_aircargo.jsonl` 100 +
`curated_cases.jsonl` 35). Метки запинены вручную (суждение по каждому запросу) в
`evaluation/adaptive_retrieval/build_phase0_labels.py`, материализованы в
`evaluation/adaptive_retrieval/phase0_labels.jsonl`. Скрипт идемпотентен:
валидирует, что каждый case_id размечен, и печатает доли.

### Таксономия

`query_class` (один из четырёх):

| класс | значение | маркеры |
|---|---|---|
| `simple` | yes/no или один короткий ответ | «Можно ли…», «Нужно ли…», off-topic-отказы |
| `factual` | один конкретный факт (число/дата/срок/одна сторона) | «Какой срок…», «Сколько…», «Кто согласует…» |
| `enumeration` | ответ — список (поля/документы/данные/доказательства/параметры/условия/шаги/причины) | «Какие поля/документы… нужны», «Перечисли…» |
| `multi-condition` | условная/процедурная логика, эскалация, чеклисты | «Когда…», «В каких случаях…», «Что проверить…» |

`needs_factcard` (bool): **TRUE только** когда ответ — перечень типов, которые
держит схема fact-card (поля / обязательные документы / нужные данные /
доказательства / параметры / обязательное содержимое / события-условия
эскалации). Перечни **шагов / причин / действий / исключений** — это
`enumeration`-класс, но `needs_factcard=FALSE` (карта не хранит процедуры). Именно
поэтому два поля разведены: не всякий список лежит в карте.

### Доли

| срез | n | simple | factual | enumeration | multi-condition | **needs_factcard** |
|---|---|---|---|---|---|---|
| **aircargo** | 100 | 6% | 9% | 44% | 41% | **44%** |
| curated | 35 | 40% | 26% | 23% | 11% | 6% |
| **ALL** | 135 | 15% | 13% | 39% | 33% | **34%** |

- **aircargo** — насыщенный enumeration/condition-домен (логистика/HR/compliance):
  44 enumeration + 41 multi-condition, simple/factual всего 15. Сильный
  mixed-complexity.
- **curated** (бытовая поддержка: гарантия/возвраты/коды ошибок) — почти весь
  simple/factual; needs_factcard всего 2 из 35.
- Воспроизвести: `python evaluation/adaptive_retrieval/build_phase0_labels.py`.

## T0.2 — baseline D2 + ретривал-статус

### Harness-валидация (mock-runtime, офлайн, Windows)

`scripts/regression_eval.py --baseline current --candidate current
--mock-experiment-runtime --no-persist` на обоих датасетах:

| датасет | total | pass_rate | infra_fail |
|---|---|---|---|
| aircargo | 100 | 100% | 0 |
| curated | 35 | 100% | 0 |

Что это доказывает: все 135 кейсов проходят pydantic-валидацию `CuratedCase`,
офлайн-харнесс рабочий на Windows. **Что это НЕ доказывает:** mock-провайдер
строит ответ ИЗ `expected.answer_contains` (`_build_mock_provider_result`) →
`answer_contains`-проверка проходит всегда. **Mock pass-rate ≠ покрытие
ретривером.** Реальный retrieval-статус — ниже, из задокументированного Kaggle
D2-baseline (тяжёлый retrieval на Windows не гоняется — запрещено).

### Ретривал-статус D2 (production-стек: structural chunking + parent-expansion w=2/3600 + reranker)

Источник — Kaggle Phase 2 (`docs/operations/2026-06-06-arm-{e,f}-*.md`,
воспроизведён 1-в-1 в cont.15/cont.18). FULL/PART/MISS = покрытие
`answer_contains`-кейвордов в top-5 (`scripts/ab_remote_contextual.py:_kw_status`).

| стек | FULL | PART | MISS |
|---|---|---|---|
| **D2 (production baseline, aircargo-100)** | **96** | 3 | 1 |

- Единственный остаточный **MISS = `aircargo-customs-clearance-fields`**
  («Какие данные нужны для таможенного оформления авиагруза?») — и это
  `enumeration` / `needs_factcard=TRUE`. Механизм: kw-чанк лежит глубоко в пуле
  (rank 27), cross-encoder не поднимает его в top-5.
- Известные рычаги query-expansion (плечи E/F) этот MISS **не закрыли** (оба
  NO-SHIP): E закрывал его расширенным реранком ценой −7 FULL коллатерали; F
  (split-query) — gain не сохранился. Fact-Card — **другой механизм** (отдельная
  коллекция, отдаём целую карту, реранк не усекает перечень полей) → это не
  повтор E/F.
- 3 PART-кейса D2-baseline **локально не восстановимы** (Kaggle-пулы вычищены в
  cont.17/18). Их ID не нужны для гейта (см. ниже); при targeting Track F —
  перемерять на Mac/Kaggle.

### Кросс-таб needs_factcard × D2-статус (aircargo, 44 needs_factcard-кейса)

| статус | needs_factcard-кейсов | примечание |
|---|---|---|
| MISS | **1** | `customs-clearance-fields` (подтверждён) |
| PART | 0..3 | 3 D2-PART локально не идентифицированы |
| FULL | ≥40 | остальные |

Итог T0.2-verify: среди needs_factcard-кейсов сейчас ровно **1 MISS**, ≤3 PART,
≥40 FULL. Ретривал-headroom на needs_factcard = 1 MISS (+ до 3 PART) — мал,
потому что D2 уже FULL 96/100.

## ГЕЙТ (Phase 0 → дальше)

Критерии плана: Fact-Card-трек — если `needs_factcard ≳10%` И на них есть
MISS/PART. Router-трек — если есть заметный mixed-complexity. Иначе STOP/NO-SHIP.

| трек | условие | факт | вердикт |
|---|---|---|---|
| **Fact-Card (Track F)** | needs_factcard ≥10% И MISS/PART на них | 44% (aircargo) ≫ 10%; 1 MISS (`customs-clearance-fields`) + ≤3 PART | **PASS (eligible)** |
| **Router (Track R)** | заметный mixed-complexity | enumeration 44% / multi-condition 41% / factual 9% / simple 6% | **PASS (eligible)** |

### Дисциплина (важно — не «дожимать»)

- **Headroom мал.** D2 = FULL 96/100. Весь измеренный потолок Fact-Card на этом
  срезе = 1 известный MISS (+ ≤3 PART). Любая постройка обязана пройти Phase-5
  NO-SHIP (recall на needs_factcard ↑ И на остальных НЕ упал И cost/latency не
  вырос), иначе NO-SHIP — как E/F.
- **Router-трек — это про cost, не про recall.** Baseline recall у потолка; смысл
  R1/R2 — заменить per-query LLM-`classify_complexity` на lightweight
  TF-IDF+SVM/MiniLM (по research ~28% экономии токенов) **при не худшем macro-F1**.
- **Train-набор роутера готов:** `phase0_labels.jsonl` (135 строк, 4 класса:
  simple 20 / factual 18 / enumeration 52 / multi-condition 45; needs_factcard
  46/135) — прямой вход для R1.

## Следующий шаг (за этим гейтом, НЕ в scope Phase 0)

Гейт пройден обоими треками, но исполнение — отдельная сессия по явному запросу:

- **Track R / R1** (lightweight-классификатор) — лёгкий, scikit-learn, **можно на
  Windows**; ближайший безопасный автономный кандидат, но это Phase 1, не Phase 0.
- **Track F / F1** (LLM-экстрактор fact-cards, ingest) — **тяжёлый, только Mac**
  (правило «no heavy на Windows»).

Phase 0 завершён. Решение о запуске Track R/F — за владельцем.

## Артефакты

- `evaluation/adaptive_retrieval/build_phase0_labels.py` — разметка (источник истины).
- `evaluation/adaptive_retrieval/phase0_labels.jsonl` — 135 размеченных кейсов / train-набор.
- Этот отчёт.
