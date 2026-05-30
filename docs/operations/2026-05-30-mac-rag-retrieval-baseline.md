# Mac retrieval baseline — R1 (English reranker on RU) proven + closed (multilingual reranker)

- Дата: 2026-05-30
- Хост: iMac `julia@192.168.1.133` (8 GB, Intel x86_64, macOS 13.7.8), Python 3.11.15 (uv venv)
- Корпус: `data/uploads/aircargo/` — **10 FAQ-документов** (подмножество, покрывает все 31 кейс)
- Датасет: `evaluation/curated_cases_aircargo.jsonl` — 31 RU-кейс
- Метрика: **retrieval keyword-coverage @ top-5** — для каждого кейса берём top-5 чанков
  ретривера, проверяем, присутствуют ли в их тексте оба ожидаемых keyword'а
  (`expected.answer_contains`). LLM не вызывается — это чистый замер retrieval.
- Чанкинг: fixed `RecursiveCharacterTextSplitter` 800/200 (`RAG_SEMANTIC_CHUNKING=false`),
  194 чанка; embeddings BGE-M3 (CPU); hybrid (dense + BM25) + RRF (k=60); `top_k=20 → top-5`.

## Результат A/B (реранкер)

| Конфигурация top-5 | FULL (оба kw) | PARTIAL | MISS |
|---|---|---|---|
| **Реранкер OFF** (vector + BM25 + RRF, top-5 по RRF) | **31/31 = 100%** | 0 | 0 |
| **Реранкер ON** (`cross-encoder/ms-marco-MiniLM-L-6-v2`, англ., дефолт) | **19/31 = 61%** | 8 | 4 |
| **Реранкер ON** (`BAAI/bge-reranker-v2-m3`, multilingual) | **31/31 = 100%** | 0 | 0 |

**Δ = −39 п.п. от включения дефолтного англ. реранкера; мультиязычный `bge-reranker-v2-m3`
восстанавливает покрытие обратно до 100%.**

### R1 ЗАКРЫТ (не «выключить реранкер», а поставить правильный)

Прогон `bge-reranker-v2-m3` (2026-05-30, iMac, two-phase — см. ниже) дал **31/31 = 100%**,
вровень с RRF-only. То есть деградация до 61% — свойство **английского** реранкера на RU,
а не реранкинга как стадии. Правильный фикс R1 — **сменить дефолтный реранкер на multilingual
`BAAI/bge-reranker-v2-m3`**, что сохраняет precision-переупорядочивание без потери RU-recall.
Реранкер-OFF — лишь воркэраунд; целевое решение — multilingual cross-encoder.

### Вывод (прямое подтверждение R1 аудита)

Гибридный retrieval + RRF на BGE-M3 находит нужный чанк в top-5 в **100%** кейсов.
Дефолтный **английский** cross-encoder реранкер (`ms-marco-MiniLM`, обучен на англ. MS MARCO),
применённый к **русскому** контенту, переранжирует кандидатов почти случайно и **выкидывает
правильные чанки из top-5**, опуская покрытие до 61%. То есть финальный precision-фильтр,
который должен повышать качество, на RU **активно его понижает**. Это эмпирическое
доказательство R1 (`audit_claude_30_05_26.md`) с before/after на реальных данных, а не гипотеза.

MISS-кейсы при реранкере ON (нужный чанк есть в RRF top-5, но реранкер его вытеснил):
`probation-extend`, `probation-dismissal`, `pdp-data`, `secret-disclosure`.

### Честная граница метода

Абсолютные 100% у RRF-only завышены масштабом подвыборки: корпус мал (10 FAQ / 194 чанка),
каждый вопрос отображается на один FAQ-документ, поэтому нужный чанк легко попадает в top-20→top-5
по RRF. На полном корпусе (201 док / ~7000 чанков) RRF-only абсолютное число будет ниже.
**Но относительная находка робастна**: английский реранкер ухудшает RU-retrieval относительно
его отсутствия — это и есть R1, и оно не зависит от размера выборки.

## Сопутствующая находка (R2 / chunk_size)

В логе ingest при дефолтном `RAG_CONTEXTUAL_HEADERS=true` — массовые
`Contextual header exceeded chunk_size for source ...; truncating chunk`: генерируемый
contextual-заголовок **длиннее chunk_size=800**, и чанк обрезается. Это живое подтверждение
связки «статичный contextual header (R2) ⨯ необоснованный chunk_size 800»: заголовок съедает
бюджет чанка и режет полезный текст.

## Производительность на 8 GB Intel

- Ingest 194 чанков (BGE-M3, CPU): **~130–230 с** (варьируется).
- **Дуэт `bge-m3` (2.3 GB) + `bge-reranker-v2-m3` (2.27 GB) одновременно НЕ влезает в 8 GB**:
  своп-тручинг (swap 1.5 GB, CPU падает до ~3%), 31-кейсовый rerank не завершился за ~30 мин.
  **Фикс — two-phase** (см. ниже): фаза A держит только bge-m3, фаза B — только reranker;
  пик ~2.3 GB, без свопа, скоринг 31 кейса (~990 пар, CPU multi-thread) = **~830 с**.
- Скачивание моделей: HF резолвит блобы через **xet-bridge** (`cas-bridge.xethub.hf.co`),
  который на этом канале даёт read-timeout/broken-pipe. Удаление пакета `hf-xet` помогло для
  `bge-m3`, но `bge-reranker-v2-m3` **всё равно** шёл через cas-bridge (и при снятом `hf-xet`,
  и при `HF_HUB_DISABLE_XET=1`). Что реально вытащило: **`snapshot_download` в retry-loop с
  resume** (`max_workers=2`) — частичные файлы дотягиваются по кускам, 2.27 GB за ~5 окон.
- Полный корпус 201 док / ~7000 чанков + reranker — лучше Colab (GPU), но retrieval-A/B на
  подвыборке two-phase'ом на 8 GB **выполним** (этим и закрыт R1).

## Следующий шаг (Colab/больше RAM)

1. ~~A/B с `BAAI/bge-reranker-v2-m3`~~ — **СДЕЛАНО на iMac (two-phase), 31/31 = 100%**, R1 закрыт.
   Целевое действие в коде: сменить дефолт `reranker_model` на multilingual (после A/B на полном корпусе).
2. Повторить на полном корпусе 201 док → честный абсолютный recall (Colab).
3. Добавить RAGAS (faithfulness/precision) с LLM (Mistral) — на 31→100–150 кейсах.

## Воспроизведение

```bash
ssh julia@192.168.1.133
cd ~/RAG_Support_Assistant && source .venv/bin/activate
# реранкер ON (дефолт):
HF_HUB_OFFLINE=1 RAG_SEMANTIC_CHUNKING=false python -u mac_retrieval_eval.py
# реранкер OFF:
HF_HUB_OFFLINE=1 RAG_SEMANTIC_CHUNKING=false RAG_RERANKER_MODEL= python -u mac_retrieval_eval.py
```
(скрипт `mac_retrieval_eval.py` — в корне репо на Mac; здесь сохранён как `.tmp/mac_retrieval_eval.py`.)

### multilingual reranker (two-phase, влезает в 8 GB)

`.tmp/ab_twophase.py` повторяет `HybridRetriever.get_relevant_documents` Steps 1–4 в два
отдельных процесса, чтобы bge-m3 и reranker не были резидентны одновременно:

```bash
# фаза A — bge-m3: ingest + RRF-кандидаты (pre-rerank) -> /tmp/ab_candidates.json, затем процесс выходит
HF_HUB_OFFLINE=1 .venv/bin/python -u .tmp/ab_twophase.py a
# фаза B — только reranker: CrossEncoder("BAAI/bge-reranker-v2-m3").predict, top-5, keyword-coverage
HF_HUB_OFFLINE=1 .venv/bin/python -u .tmp/ab_twophase.py b
```

Предзагрузка reranker (xet-канал флапает): `snapshot_download("BAAI/bge-reranker-v2-m3",
max_workers=2)` в retry-loop с resume.
