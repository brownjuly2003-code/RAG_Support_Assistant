# Free R7 baseline — retrieval quality measured, LLM-judged metrics blocked (no budget)

- Дата: 2026-06-03
- Цель: измерить качество RAG (audit `docs/audits/audit_claude_03_06_26.md` §11 #0, R7) **бесплатно**, без платных API и без heavy-железа.
- Корпус/датасет: aircargo, 100 RU curated-кейсов (`evaluation/curated_cases_aircargo.jsonl`).
- Контексты: **закэшированы** на iMac (`/tmp/ab_candidates.json`, скопированы в `.tmp/`) —
  per-case RRF top-5 кандидаты (fixed 800/200 чанкинг, БЕЗ production-реранка bge-reranker-v2-m3,
  который не запускается на этом хосте). Переингест не нужен.

## Результат — retrieval-качество (free, без LLM)

`context_precision` / `context_recall` (`evaluation/ragas_eval.py`) считаются **без LLM и без
сгенерированного ответа** — только вопрос + retrieved-контексты + keyword'ы кейса:

| Метрика (RRF top-5, no rerank) | mean | median |
|---|---|---|
| context_precision | **0.488** | 0.488 |
| context_recall | **0.785** | 1.000 |

- **74/100** кейсов — полный recall (все keyword'ы в top-5), **17/100** — нулевой, 9 частичных.
- Кросс-проверка: совпадает с reranker A/B (`2026-06-02-mac-fullcorpus-reranker-ab.md`, RRF-only
  top-5 = 74% FULL) → recall-сигнал устойчив, не артефакт одного прогона.
- 17 нулевых — систематический gap, преимущественно `*-required-fields` / escalation-кейсы
  (ожидается список конкретных полей): `dangerous-goods-fields`, `customs-clearance-fields`,
  `waybill-escalation-events`, `incident-response-required-fields`, `access-control-review`,
  `driver-hours-required-fields`, `warehouse-3pl-required-fields`, `perishable-temperature-controls`,
  `oversized-permit-route`, и др. Нужный фрагмент не доходит до RRF top-20 — это recall ретривера
  (не реранк, не чанкинг: structural A/B его не закрыл). Кандидат на R5 (BGE-M3 native sparse) /
  expand-query / расширение корпуса по этим темам.

## Что НЕ удалось бесплатно: LLM-judged faithfulness / answer_relevancy

Эти метрики требуют (а) сгенерированного ответа и (б) LLM-судьи. Бесплатный hosted-LLM из этого
окружения (RU IP, без карты) **недостижим** — проверено напрямую, 3 провайдера:

| Провайдер | Endpoint | Результат |
|---|---|---|
| Groq | `api.groq.com` (OpenAI-compat) | **403** «Access denied. Please check your network settings» — гео-блок РФ |
| OpenRouter | `…/llama-3.3-70b-instruct:free` | **429** «temporarily rate-limited upstream» — общий free-пул задушен |
| Gemini | `generativelanguage.googleapis.com` (оба ключа, 2.0-flash) | **429 RESOURCE_EXHAUSTED**, `generate_content_free_tier_requests limit: 0` — free-tier для региона/проектов = ноль запросов (нужен billing) |

Вывод: LLM-judged faithfulness/answer_relevancy для R7 **бесплатно отсюда получить нельзя** —
нужен либо рабочий VPN (для Groq), либо billing (деньги — нет), либо Gemini-ключ с ненулевым
free-tier. Это среда, не код: пайплайн рабочий (context-метрики посчитаны).

## Инструмент готов (one-command full R7, когда появится рабочий LLM)

`scripts/aircargo_ragas_free.py` — переиспользует `evaluation.ragas_eval.RAGEvaluator` +
aircargo-renderer. Free-LLM (Groq/OpenRouter/Gemini, ключ только из env) как генератор+судья
поверх cached-контекстов; client-side спейсинг + retry/backoff под free-tier RPM. Запуск:

```bash
export GEMINI_API_KEY=...   # или GROQ_API_KEY (через VPN) / OPENROUTER_API_KEY
python scripts/aircargo_ragas_free.py --provider gemini --max-cases 100
# отчёт -> reports/ragas/<run_id>-aircargo-ragas.{md,json}
```

При появлении рабочего ключа/VPN полный R7 (faithfulness+relevancy+precision+recall на 100 кейсах)
— один прогон, ~10-15 мин. Контексты уже закэшированы.
