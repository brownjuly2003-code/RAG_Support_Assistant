# Research: RAG evaluation metrics for production

## Goal
Оценить, насколько надёжны текущие метрики в `evaluation/ragas_eval.py` (keyword-overlap proxies),
и выяснить: что используется в production-RAG системах поддержки вместо/рядом с RAGAS.

## Background: что сейчас

`evaluation/ragas_eval.py` реализует 4 метрики **без LLM-вызовов**:
- `faithfulness` — доля предложений ответа, у которых ≥50% content-слов есть в контексте
- `answer_relevancy` — доля слов вопроса (≥3 символа), найденных в ответе
- `context_precision` — weighted (1/rank) keyword overlap между вопросом и каждым документом
- `context_recall` — доля expected_keywords, найденных в объединённом контексте

**Проблема:** эти proxy-метрики слабые:
- Короткий правильный ответ «Нет, это невозможно» даёт низкий faithfulness
- answer_relevancy не улавливает синонимы и парафразы
- context_precision не различает документы по смыслу — только по ключевым словам

## Research questions

### Q1: Насколько надёжны keyword-based прокси?

**Ответ:**
```
[Correlation coefficient keyword vs LLM judge: в RAG-специфичном бенчмарке mtRAG (TACL 2025) алгоритмический reference-based aggregate (RBalg: Bert-Recall + Bert-K-Precision + Rouge-L) дал weighted Spearman 0.24 с human win-rate, а LLM judge RBllm — 0.33. В смежной задаче long-form response assessment (COLING 2025) ROUGE-1 и ROUGE-L дали Pearson 0.19 и 0.14 с human acceptability, тогда как LLM judges дали 0.70 и 0.72.]
[Conclusion: keyword proxies недостаточны как основной production-сигнал для support-ticket RAG. Их можно оставить как дешёвый smoke-test или drift-signal, но не как главный индикатор качества, потому что они слабо ловят парафразы, синонимы и короткие корректные ответы.]
[Source: mtRAG, TACL 2025 — https://aclanthology.org/2025.tacl-1.36.pdf ; Quantifying the Influence of Evaluation Aspects on Long-Form Response Assessment, COLING 2025 — https://aclanthology.org/2025.coling-main.588.pdf ; дополнительный caveat по качеству judge-моделей: ContextualJudgeBench, ACL 2025 — https://aclanthology.org/2025.acl-long.470/]
```

Краткий вывод по источникам: автоматические lexical/heuristic метрики дают слабый или умеренный сигнал, а LLM judges обычно ближе к человеческой оценке, но сами тоже нестабильны в контекстных задачах. Поэтому production-подход обычно гибридный, а не "либо keyword, либо judge".

---

### Q2: RAGAS package — что реально нужно для его запуска?

**Ответ:**
```
[LLM calls per test case: зависит от метрик. По официальным описаниям Ragas, `Faithfulness` сначала выделяет claims из ответа, затем проверяет их на support в retrieved context; `Response Relevancy` по умолчанию генерирует 3 artificial questions и считает cosine similarity. Практический вывод: для пары `Faithfulness` + `Response Relevancy` это не "один вызов на кейс", а обычно минимум 2-3 LLM-операции на кейс плюс embedding-операции. Для 100 test cases стоит ожидать порядка 200-300+ judge-операций до учёта retries и длины ответа. Это вывод по структуре метрик, а не прямая цифра из docs.]
[Ollama support: да. Официальный quickstart Ragas показывает `llm_factory(\"mistral\", provider=\"ollama\", base_url=\"http://localhost:11434\")`; в актуальных docs также показан OpenAI-compatible путь для локальных моделей.]
[Alternative: ragas без LLM — частично возможно. В Ragas есть non-LLM метрики (`NonLLMStringSimilarity`, `BLEU`, `ROUGE`, `Exact Match`, `String Presence`), но классические RAG-метрики (`Faithfulness`, `Response Relevancy`, context-метрики) опираются на LLM и/или embeddings. То есть "ragas без LLM" возможно только если сознательно выбрать non-LLM subset, а не стандартный RAG eval stack.]
[Source: https://docs.ragas.io/en/latest/references/evaluate/ ; https://docs.ragas.io/en/latest/getstarted/evals/ ; https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ ; https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/answer_relevance/ ; https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ ; https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/traditional/]
```

---

### Q3: Альтернативы RAGAS — DeepEval, TruLens, LangSmith

**DeepEval:**
```
[Strengths vs RAGAS: сильнее как eval-framework для разработки и CI: pytest-native workflow, единый набор single-turn/multi-turn/RAG metrics, component-level и online/offline сценарии через Confident AI.]
[LLM-free mode: для built-in RAG metrics — скорее нет. Официальные docs Confident AI/DeepEval прямо говорят, что их metrics используют LLM-as-judge; детерминированные проверки у них идут через custom code-evals и отдельные task-specific метрики, а не через стандартные RAG metrics.]
[Russian support: зависит от judge-модели. Метрики принимают `model` как строку или custom object типа `DeepEvalBaseLLM`, так что локальную/русскоязычную модель подключить можно.]
[Source: https://www.confident-ai.com/docs/documentation/metrics/introduction ; https://www.confident-ai.com/docs/metrics/single-turn/answer-relevancy-metric ; https://www.confident-ai.com/docs/metrics/single-turn/contextual-precision-metric ; https://www.confident-ai.com/docs/metrics/single-turn/contextual-recall-metric ; https://www.confident-ai.com/docs/metrics/single-turn/faithfulness-metric]
```

**TruLens:**
```
[Strengths: силён в instrumentation + observability + custom feedbacks. У него есть RAG Triad (context relevance, groundedness, answer relevance), встроенный dashboard и OpenTelemetry-совместимость.]
[LLM-free mode: частично да. Стандартный RAG Triad строится вокруг feedback provider/LLM, но в TruLens есть embedding-based feedback functions (`cosine_distance`, `manhattan_distance`, `euclidean_distance`) и ground-truth агрегаторы/метрики, поэтому LLM-free или hybrid eval собирать можно.]
[Production fit: высокий. TruLens явно позиционируется как evals + tracing слой для production и даёт встроенный dashboard для leaderboard/trace-level анализа.]
[Source: https://www.trulens.org/getting_started/core_concepts/rag_triad/ ; https://www.trulens.org/reference/trulens/feedback/embeddings/ ; https://www.trulens.org/component_guides/evaluation/feedback_implementations/custom_feedback_functions/ ; https://www.trulens.org/getting_started/dashboard/ ; https://www.trulens.org/cookbook/models/local_and_OSS_models/ollama_quickstart/]
```

**LangSmith:**
```
[Strengths: самый сильный вариант для production process-а, а не только метрик. Он объединяет offline datasets, online evaluators, human review, code rules, pairwise comparison и может оценивать intermediate retrieval steps.]
[Cost: зависит от evaluator mix. Code evaluators и heuristic rules почти бесплатны в исполнении, а LLM-as-judge добавляет обычную стоимость judge-модели. Docs отдельно рекомендуют sampling/filtering для online evaluators, чтобы контролировать расходы.]
[Fit for local/self-hosted: да. Актуальная документация LangSmith указывает cloud, hybrid и self-hosted варианты установки.]
[Source: https://docs.langchain.com/langsmith/evaluation ; https://docs.langchain.com/langsmith/evaluation-concepts ; https://docs.langchain.com/langsmith/code-evaluator-sdk ; https://docs.langchain.com/langsmith/code-evaluator-ui ; https://docs.langchain.com/langsmith/evaluate-on-intermediate-steps ; https://docs.langchain.com/langsmith]
```

---

### Q4: Production-ready подход без per-query LLM overhead

**Ответ:**
```
[Рекомендуемый подход для production без per-query LLM: держать online monitoring дешёвым и без judge-LLM — embedding similarity + retrieval diagnostics + business signals, а более дорогой LLM-as-judge запускать оффлайн по sampled dataset или weekly benchmark.]
[Библиотека/инструмент: для online — собственная embedding-метрика на `sentence-transformers`/BGE-M3 cosine similarity или embedding feedbacks в TruLens; для offline benchmark и human loop — LangSmith/TruLens/Ragas в batch-режиме.]
[Overhead (ms per request): вывод по типичным embedding-forward-pass, а не прямая цифра из docs: обычно десятки миллисекунд на пару question/answer на GPU и низкие сотни миллисекунд на CPU, то есть значительно дешевле judge-LLM на каждый ответ.]
[Source: https://www.trulens.org/reference/trulens/feedback/embeddings/ ; https://docs.langchain.com/langsmith/evaluation-concepts ; https://docs.langchain.com/langsmith/evaluation ; https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/traditional/]
```

Практически для этого проекта это означает:
- online: `keyword proxies` оставить как дешёвую диагностику, но добавить embedding-based `answer_relevancy`
- offline: гонять более дорогой benchmark на curated set, а не на каждом user query
- sampled human review: разбирать низкий quality, human-route и негативный feedback

---

### Q5: Метрики специфичные для support-ticket RAG

**Ответ:**
```
[Топ-3 метрики для support RAG по приоритету: 1) Faithfulness / groundedness, 2) Escalation accuracy (верно ли выбрали auto vs human), 3) Resolution/completeness proxy (закрыл ли ответ проблему без повторного обращения).]
[Как измерять escalation accuracy без ground truth? Через outcome-based retrospective labels: если `auto` ответ был потом исправлен человеком, reopened или привёл к повторному тикету — это false negative маршрутизации; если `human` эскалация регулярно закрывается без добавочной работы оператора — это false positive. Дополнительно нужен sampled human audit на спорных кейсах.]
[Source: приоритет faithfulness подтверждён RAG-specific benchmarking в mtRAG; необходимость контекстно-зависимых rubric/judge-подходов подтверждена ContextualJudgeBench; loop через human review/online feedback — LangSmith evaluation concepts. Для FCR/escalation это вывод из support use case, а не отдельная академическая метрика из одного источника.]
```

---

## Output: Recommendation

```
РЕКОМЕНДАЦИЯ:
- Текущие keyword proxies: дополнить, а не оставлять в одиночку, потому что они дешёвые и полезны как guardrail/diagnostic signal, но слишком слабо коррелируют с реальным качеством ответа в задачах с парафразами и короткими корректными ответами.
- Добавить embedding-based метрику: да — конкретно semantic similarity на локальной multilingual embedding-модели, лучше всего на уже используемом в проекте BGE-M3 или совместимой sentence-transformers модели для `answer_relevancy`.
- RAGAS пакет: использовать ограниченно, потому что его классические RAG-метрики дают более качественный сигнал, но слишком дороги для per-query evaluation; годится для offline benchmark и sampled audits, а не для online scoring каждого ответа.
- Для production monitoring: keyword + embeddings + route/outcome/business signals + user feedback, без judge-LLM на каждый запрос.
- Для offline benchmark: curated support dataset, batch eval с Ragas/TruLens/LangSmith и периодическим human audit на low-score / high-risk кейсах.
```

## Notes

- `evaluation/ragas_eval.py` сегодня реализует ровно тот тип cheap proxies, который имеет смысл оставить как baseline и fallback.
- Следующий логичный шаг для проекта: добавить embedding-based `answer_relevancy` без удаления текущего keyword pipeline.

