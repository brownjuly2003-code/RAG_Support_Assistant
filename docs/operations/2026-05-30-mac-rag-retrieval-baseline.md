# Mac retrieval baseline — R1 (English reranker on RU) proven on real data

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

**Δ = −39 п.п. от включения дефолтного реранкера.**

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
- BGE-M3 (~2.27 GB) скачивается; HF **xet-bridge** (`cas-bridge.xethub.hf.co`) на этом канале
  даёт read-timeout/broken-pipe (~16 KB/s). Фикс: **снести пакет `hf-xet`** из venv →
  huggingface_hub идёт через обычный CDN (~1.65 MB/s). `HF_HUB_DISABLE_XET=1` cli **игнорирует** —
  именно удаление пакета помогает.
- Полный корпус 201 док / ~7000 чанков + тяжёлый `bge-reranker-v2-m3` (2.3 GB) — за пределами
  комфортного RAM-бюджета 8 GB; такой прогон → Colab.

## Следующий шаг (Colab/больше RAM)

1. Тот же A/B, но третья рука — `BAAI/bge-reranker-v2-m3` (multilingual): ожидаем восстановление
   до ~100% и выше при росте корпуса. Это закрытие R1 (не просто «выключить реранкер»,
   а поставить правильный multilingual).
2. Повторить на полном корпусе 201 док → честный абсолютный recall.
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
