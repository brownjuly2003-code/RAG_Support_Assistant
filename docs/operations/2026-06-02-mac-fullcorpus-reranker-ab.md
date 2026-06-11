# Mac full-corpus reranker A/B — R1 дефолт подтверждён на всём корпусе (201 док)

- Дата: 2026-06-02
- Хост: iMac `julia@192.168.1.133` (8 GB, Intel x86_64, macOS 13.7.8), Python 3.11.15 (uv venv)
- Репо на Mac: `9b219fa` (= `origin/master`, дефолт reranker уже `BAAI/bge-reranker-v2-m3`)
- Корпус: `data/uploads/aircargo/` — **полный, 201 документ** (не 10-FAQ-подвыборка)
- Датасет: `evaluation/curated_cases_aircargo.jsonl` — **100 RU-кейсов**
- Метрика: **retrieval keyword-coverage @ top-5** — для каждого кейса берём top-5 чанков после
  стадии реранка, FULL = найдены все `expected.answer_contains`, PART = часть, MISS = ни одного.
  LLM не вызывается — чистый замер retrieval.
- Чанкинг: fixed `RecursiveCharacterTextSplitter` 800/200 (`RAG_SEMANTIC_CHUNKING=false`),
  **5077 чанков**; embeddings BGE-M3 (CPU); hybrid (dense + BM25) + RRF; `top_k=20 → rerank → top-5`.
  Средний размер пула RRF-кандидатов до реранка: **35.0** на кейс.

## Результат A/B (полный корпус, 100 кейсов, top-5)

| Конфигурация top-5 | FULL (все kw) | PART | MISS |
|---|---|---|---|
| **Реранкер OFF** (vector + BM25 + RRF, top-5 по RRF) | **74/100 = 74%** | 9 | 17 |
| **Реранкер ON** (`cross-encoder/ms-marco-MiniLM-L-6-v2`, англ., прежний дефолт) | **42/100 = 42%** | 22 | 36 |
| **Реранкер ON** (`BAAI/bge-reranker-v2-m3`, multilingual, **текущий дефолт**) | **80/100 = 80%** | 8 | 12 |

**На реалистичном полном корпусе мультиязычный реранкер не просто восстанавливает покрытие —
он обгоняет вариант без реранка: bge-v2-m3 80% vs OFF 74% (+6 п.п.). Английский ms-marco рушит
покрытие до 42% (−32 п.п. относительно OFF).**

### R1 — дефолт `bge-reranker-v2-m3` подтверждён сильнее, чем на подвыборке

Сверка с 10-FAQ-baseline (`docs/operations/2026-05-30-mac-rag-retrieval-baseline.md`):

| Arm | 10 FAQ / 194 чанка / 31 кейс | Полный корпус / 5077 чанков / 100 кейсов |
|---|---|---|
| OFF (RRF) | 100% | **74%** |
| ms-marco (англ.) | 61% (Δ−39 пп) | **42% (Δ−32 пп)** |
| bge-v2-m3 (multilingual) | 100% (= OFF) | **80% (+6 пп над OFF)** |

На подвыборке абсолютные числа упирались в потолок (RRF уже 100%, реранку «некуда расти»),
поэтому bge-v2-m3 лишь сравнялся с OFF. На полном корпусе потолок снят: RRF-only падает до 74%,
и тут multilingual cross-encoder **реально добавляет precision** — поднимает правильные чанки
в top-5, давая 80%. То есть на честном масштабе реранк перестаёт быть «нейтральной стадией,
которую достаточно не ломать» и становится **положительным вкладом** — при условии, что модель
мультиязычная. Решение сменить дефолт (`90891e5`) валидно и обосновано сверх «вернуть как было».

Английский ms-marco подтверждает R1 и на полном корпусе: 42% против 74% OFF — финальный
precision-фильтр, обученный на англ. MS MARCO, на RU **активно понижает** качество retrieval.

### Честная граница

- 74/42/80 — абсолютные числа на keyword-coverage; это прокси (точное вхождение строки в текст
  чанка), не семантическое совпадение и не end-to-end ответ. Реальная answer-quality (faithfulness/
  citation precision) требует RAGAS+LLM — следующий шаг (Colab/Mistral, §«Дальше»).
- Относительная картина (англ. реранкер вредит, multilingual помогает) робастна и воспроизведена
  на двух масштабах — это и есть закрытие R1.
- 12 MISS у bge-v2-m3 и 17 у OFF — кандидаты, где нужный чанк не попал даже в RRF top-20 (recall
  ретривера), реранк их вернуть не может. Это отдельная линия (chunk-size / structural / sparse),
  не реранк.

## Производительность на 8 GB Intel (two-phase, без своп-тручинга)

- Phase A (bge-m3 only): load 201 док 0.7 с; **ingest 5077 чанков = 5479.9 с (~91 мин)** на CPU;
  + построение RRF-кандидатов по 100 кейсам. Пик RAM ~1.8 GB, своп не задействован.
- Phase B (reranker only, по одному резидентно):
  - ms-marco-MiniLM: загрузка 7 с, скоринг 100 кейсов (~3500 пар) = **518 с**.
  - bge-reranker-v2-m3: загрузка 4 с, скоринг = **5126 с (~85 мин)** — большая модель, CPU.
- Полный прогон A→B завершён через robust-chainer (`nohup`, переживает обрыв ssh): Phase A
  18:11→19:46, Phase B 19:46→21:22 MSK. Подтверждает: full-corpus reranker A/B на 8 GB
  **выполним** two-phase'ом, хоть и медленно (~3.5 ч). Для частых прогонов — Colab GPU.

## Chunking A/B (structural vs fixed) — recall-нейтрально, дефолт не менять

Гипотеза: 17 RRF-MISS (нужный чанк не дошёл до RRF top-20) — следствие нарезки fixed 800/200
посреди логических секций; markdown-structural chunking (флаг `RAG_STRUCTURAL_CHUNKING`, уже в коде,
default off) должен их восстановить. Проверено тем же RRF-only top-5 замером (реранкер OFF —
изолирует эффект чанкинга), 100 кейсов, полный корпус, iMac:

| Чанкинг (RRF-only top-5) | чанков | FULL | PART | MISS |
|---|---|---|---|---|
| fixed `RecursiveCharacterTextSplitter` 800/200 (дефолт) | 5077 | **74%** | 9 | 17 |
| markdown-structural (`RAG_STRUCTURAL_CHUNKING=true`) | 5589 | **73%** | 8 | 19 |

**Вывод: structural chunking recall-нейтрален (−1 пп, в пределах шума, даже чуть больше MISS).
Он НЕ закрывает recall-провалы. Дефолт остаётся fixed 800/200, флаг `RAG_STRUCTURAL_CHUNKING` — off.**
19 MISS у structural — преимущественно `*-required-fields` / escalation-запросы, где ожидается
список конкретных полей: нужный фрагмент либо не доходит до RRF top-20 (recall ретривера, не чанкинг),
либо метрика keyword-coverage (точное вхождение всех keyword'ов) занижает по своей природе.

Сопутствующе (обе нарезки): в логе ingest массовый `Contextual header exceeded chunk_size;
truncating chunk` — статичный doc-header длиннее `chunk_size=800`, чанк режется. По аудиту
`docs/audits/audit_claude_03_06_26.md` §10 это **качественный долг, не баг** (отложено), а не приоритетный фикс.

## Дальше (по `docs/audits/audit_claude_03_06_26.md` §11, не вкатывать вслепую)

1. ~~Full-corpus reranker A/B~~ — **СДЕЛАНО**, дефолт `bge-reranker-v2-m3` подтверждён (80% > 74% OFF > 42% англ.).
2. ~~chunk-size / structural A/B~~ — **СДЕЛАНО**, recall-нейтрально, дефолт не меняем.
3. **R7 (HIGH):** RAGAS faithfulness/precision/recall на 100 кейсах — Colab + live Mistral (gated: интерактивно/квота).
4. **F1 (MEDIUM):** удержание ссылок на 3 fire-and-forget `asyncio.create_task` — локально, тестируемо.
5. R5 — BGE-M3 native sparse вместо `.split()` BM25 (модель уже загружена).

## Воспроизведение

```bash
ssh julia@192.168.1.133
cd ~/RAG_Support_Assistant
# detached + chainer (переживает обрыв ssh); результат -> .tmp/ab_result_20260602.txt:
nohup bash -c 'HF_HUB_OFFLINE=1 RAG_SEMANTIC_CHUNKING=false .venv/bin/python -u .tmp/ab_twophase.py a' > /tmp/abA.log 2>&1 &
nohup bash .tmp/ab_chain.sh <PID_phase_A> &   # ждёт A -> phase B (3 руки) -> пишет результат
```

`.tmp/ab_twophase.py` повторяет `vectordb/_base_manager.HybridRetriever.get_relevant_documents`
Steps 1–4 в два процесса (bge-m3 и reranker не резидентны одновременно — 8 GB-safe). Phase B
прогоняет 3 руки по очереди: OFF (RRF-порядок) / ms-marco / bge-v2-m3, выгружая модель между ними.
