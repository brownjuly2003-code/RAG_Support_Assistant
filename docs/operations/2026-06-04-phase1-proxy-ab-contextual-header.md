# Phase 1 proxy A/B — contextual-header направление ПОДТВЕРЖДЕНО (12/13 целевых ↑), обрезка тела чанка ВРЕДИТ (починена)

- Дата: 2026-06-04
- План: `docs/plans/2026-06-03-overcome-retrieval-barrier.md` (Phase 1 — дешёвый прокси-A/B
  под лимитом <1GiB на Windows-хосте, go/no-go перед тратой remote-ресурса).
- Вопрос: поднимает ли structural chunking + heading-path contextual header (`fc4ad0e`)
  целевые чанки класса `*-required-fields` в RRF-ранге?
- Скрипт: `.tmp/ab_proxy_minilm.py` (gitignored), two-phase на каждое плечо
  (encode-процесс с моделью ≈1.0 GiB peak / eval-процесс без torch ≈0.3 GiB), чекпойнты
  матрицы каждые 512 чанков, RAM-watchdog.

## Setup

- Корпус: `data/uploads/aircargo/` — 201 RU-док, тот же, что в Mac BGE-M3 baseline.
- Кейсы: `evaluation/curated_cases_aircargo.jsonl` — 100, метрика как в прежних A/B:
  keyword-coverage @ top-5 (FULL/PART/MISS) + **co-occur rank** (первый кандидат пула,
  содержащий ВСЕ `answer_contains`) — то же определение, что в rank-grade диагнозе
  (`2026-06-03-r7-llm-judged-baseline.md`).
- Ретривал: зеркало `HybridRetriever` шагов 1-3 (dense top-20 + BM25 top-20 → `_rrf_merge`),
  реранкер OFF. Dense — точный brute-force cosine по нормированным эмбеддингам
  (детерминированный; продакшн-ANN не нужен для рангового сравнения).
- Прокси-эмбеддер: `paraphrase-multilingual-MiniLM-L12-v2` (RU-способный, ~470MB).
  Осознанное отклонение от plan-формулировки `all-MiniLM-L6-v2`: тот EN-only, на RU-корпусе
  dense-сторона выродилась бы в шум и A/B сместился бы к чистому BM25. Дух плана —
  «sub-1GiB прокси» — сохранён.

## Плечи

| Плечо | Чанкинг | Header | Обрезка тела `[:chunk_size]` | Чанков |
|---|---|---|---|---|
| **A** (зеркало baseline) | fixed 800/200 | doc-name (`[Контекст: Из документа {file}]`) | да (production wrapper) | 5077 — совпало с Mac-прогоном 1-в-1 |
| **B** (фикс как был бы отгружен) | structural (h1..h4) | heading-path | да | 5589 |
| **C** (изоляция вреда обрезки) | structural | heading-path | **нет** | 5589 |

Header в плече A — не гипотеза: кэш Mac-baseline (`.tmp/ab_candidates.json`) несёт
`[Контекст: Из документа …]` на 300/300 проверенных кандидатах (production-дефолт
`contextual_headers=true`, пинован тестом `test_contextual_headers_enabled_by_default` —
утверждение «default off» в cont.10 было неверным; off по умолчанию только
`structural_chunking`).

## Результат — headline (прокси-абсолюты, сравнивать только между плечами)

| Плечо | FULL @ top-5 | PART | MISS |
|---|---|---|---|
| A | 65/100 | 11 | 24 |
| B | 70/100 | 10 | 20 |
| **C** | **73/100** | 7 | 20 |

## 13 диагноз-целей — co-occur rank по плечам

| case | A | B | C | top5 A/B/C |
|---|---|---|---|---|
| dangerous-goods-fields | 5 | 3 | 3 | FULL/FULL/FULL |
| customs-clearance-fields | — | — | — | MISS/MISS/MISS |
| waybill-first-mile-fields | — | 3 | 3 | PART/FULL/FULL |
| access-control-review | 4 | 1 | 1 | FULL/FULL/FULL |
| driver-hours-required-fields | — | 21 | 23 | MISS/MISS/MISS |
| perishable-temperature-controls | — | — | 13 | MISS/MISS/MISS |
| cross-border-required-fields | 3 | **—** | 1 | FULL/**PART**/FULL |
| waybill-escalation-events | 32 | 20 | 20 | MISS/MISS/MISS |
| warehouse-3pl-required-fields | 26 | 18 | 16 | MISS/MISS/MISS |
| oversized-permit-route | 35 | **—** | 1 | MISS/**PART**/FULL |
| fuel-supply-evidence | 12 | 1 | 1 | MISS/FULL/FULL |
| gps-monitoring-required-fields | 6 | **—** | 5 | MISS/**MISS**/FULL |
| weight-control-required-fields | 31 | 25 | 14 | MISS/MISS/MISS |

(«—» = ключи не сошлись ни в одном кандидате пула top-40.)

**A→C: 12/13 улучшены, 0 регрессий** — включая 3 спасения из «вне пула» в top-5
(waybill-first-mile →3, oversized-permit 35→1, fuel-supply 12→1) и 2 спасения в пул
(driver-hours →23, perishable →13), которые в production добивает реранкер
(bge-v2-m3 уже показывал 80% top-5 из пула vs 74% без).

**A→B: 8/13 улучшены, 3 регрессии — и все 3 вызваны обрезкой тела.** Root-cause доказан
по пулам: в B второй keyword (`vehicle_tir_carnet`, `escort_vehicle_count`,
`gps_device_id`) **физически отсутствует во всём RRF-пуле** — `[:chunk_size]` срезал
хвостовые строки field-таблиц (обрезка била 1829/5589 = 33% structural-чанков; в плече A —
1443/5077 = 28%). C находит те же доки на rank 1-5.

## Решения

1. **GO на Phase 2** (production-подтверждение BGE-M3 + bge-reranker-v2-m3, Colab/iMac):
   направление contextual-header подтверждено относительным сигналом на прокси.
2. **Обрезка тела чанка починена ДО Phase 2** — commit `4844094`: тело сохраняется
   целиком, превышение ограничено клампом самого header'а до 200 символов (теперь в обоих
   путях `_base_manager`), warning-спам (1443 строки/ингест) заменён одним summary-INFO.
   После фикса production-путь текстуально совпадает с плечом C (header'ы корпуса ≤200) —
   отдельный re-run плеча B′ не нужен.
3. Phase 2 плечо сравнения: **A (fixed+doc-name header) vs C-конфиг
   (`RAG_STRUCTURAL_CHUNKING=true` + дефолтный `RAG_CONTEXTUAL_HEADERS`)** на
   BGE-M3 + реранк, recall@top-5 на 100 кейсах + re-run R7 LLM-judged (Mistral).

## Остаточный промах: customs-clearance-fields (— во всех плечах)

Целевой чанк в C существует и идеален (`05_tlog_regulation_customs_clearance.md ›
Порядок действий › 2. Обязательные поля`, оба kw, 931 chars), правильный ДОК есть в пуле
на позиции 2 — но другим чанком (intro), сама секция не дотянулась в top-40. Запрос
говорит «данные», якорь — «поля». Кандидаты: parent-child (`RAG_PARENT_CHILD` уже
заведён) — родительский док вернул бы секцию; или реранкер на расширенном пуле. НЕ
блокер Phase 2; отдельная строка для Phase 3.

## Честные границы прокси

- MiniLM-L12 max_seq=128 токенов: dense-эмбеддинг видит ~первые 450-500 символов чанка —
  это смещение В ПОЛЬЗУ препендированного якоря. BGE-M3 (8K) embeds весь чанк, поэтому
  dense-лифт на production может быть меньше. BM25-половина и co-occur-метрика считаются
  по полному тексту — спасения «в пул» этим смещением не объясняются. Phase 2 обязателен.
- Прокси-baseline ≠ production-baseline по кейс-миксу (65% vs 74% RRF-only): три из «7 deep»
  у прокси и так находились (dangerous 5, access-control 4, cross-border 3) — поэтому
  сравнение строго внутрипрокси, A↔B↔C, а не «old→new».
- Co-occur rank — лексический прокси релевантности (как и весь keyword-coverage стек
  прежних A/B).

## Воспроизведение

```
python .tmp/ab_proxy_minilm.py encode A   # ~7-16 мин CPU, чекпойнты .tmp/ab_proxy_A_mat_part*.npy
python .tmp/ab_proxy_minilm.py eval A     # секунды, без torch; -> .tmp/ab_proxy_A.json
# аналогично B, C
```

RAM-факт: encode-процесс пик ~1.0 GiB (watchdog warn 0.95 / abort 1.10), eval ~0.3 GiB;
хост 15.5 GiB, во время прогона деградации не было. Первый одно-процессный вариант
скрипта упал на watchdog 1024 MiB ПОСЛЕ 16-мин encode (BM25 добавил последние +30 MiB) —
отсюда two-phase + чекпойнты.
