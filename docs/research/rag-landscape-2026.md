# RAG Landscape 2026: What's Still Relevant

*Researched: 2026-04-04*

---

## Verdict: Is Classic RAG Still Relevant?

Классический RAG не умер — он стал **базовым слоем** более сложных систем. По данным Forrester 2025,
RAG стал дефолтной архитектурой для корпоративных knowledge assistants. Рынок RAG:
$1.96 млрд в 2025 → $40.34 млрд к 2035 (CAGR 35.31%, ResearchAndMarkets, октябрь 2025).

Long-context LLMs и RAG — не конкуренты, а комплементарные инструменты:
- LC-модели выигрывают на Wikipedia-based QA и малых корпусах (<200K токенов)
- RAG выигрывает на dialogue-based queries и динамических knowledge bases
- 71% компаний, начавших с «context-stuffing», добавили vector retrieval в течение 12 месяцев
  (Gartner Q4 2025 survey, 800 предприятий)

**Короткий ответ:** классический single-hop RAG уходит из продакшена — не потому что устарел,
а потому что вырос. Побеждает Agentic RAG + Hybrid Search + Reranking.

---

## Почему классический RAG под давлением

| Проблема | Чем отвечает рынок | Зрелость |
|----------|-------------------|---------|
| Chunking разрывает контекст | Semantic chunking, parent-child chunks | Продакшн |
| Single-hop не справляется с multi-hop вопросами | Agentic RAG, GraphRAG | Продакшн |
| Keyword mismatch | Hybrid BM25+vector, HyDE | Продакшн |
| Irrelevant chunks в промпт | Cross-encoder reranking | Продакшн |
| Плохой ответ молча уходит к пользователю | Self-RAG / Corrective RAG | Продакшн |
| Весь корпус не помещается в контекст | Long-context + RAG hybrid | Ранний продакшн |

---

## Топ-5 методов в продакшене (2025–2026)

### 1. Agentic RAG — лидер роста

Вместо фиксированного single-hop retrieval — автономные агенты, которые планируют
множество шагов поиска, выбирают инструменты, рефлексируют над промежуточными ответами.

**Почему востребован:** улучшает обработку сложных запросов на 35–50%
(LangSmith production traces, 150 предприятий, Q4 2025).
**Цена:** latency +200–400 мс.
**Кто использует:** LangChain/LangGraph, Microsoft Copilot, Workday.
**Наш проект:** частично реализован — LangGraph pipeline с Self-RAG retry loop.
Следующий шаг: добавить tool-use (web search, FAQ lookup) как дополнительные инструменты агента.

### 2. GraphRAG — для корпусного понимания

Строит граф сущностей и отношений поверх корпуса — позволяет отвечать на «глобальные» вопросы
(«какие темы проходят через весь документ?», «как связаны сущности A и B?»).

**Данные:** Microsoft open-sourced в 2024, enterprise adoption ускорился в 2025.
Multi-hop recall +6.4 пункта, снижение галлюцинаций на 20–30% (arxiv 2506.00054).
**Кто использует:** Microsoft Azure AI Search, Haystack, compliance-heavy enterprise.
**Наш проект:** не реализован. Полезен если база знаний содержит связанные сущности
(продукты, ошибки, процедуры). Дорого в построении — рекомендую отложить до роста корпуса (>10K doc).

### 3. Hybrid Search (BM25 + Vector + RRF) — production default

BM25 даёт точный keyword matching, векторный поиск — семантическое понимание.
Reciprocal Rank Fusion (RRF) объединяет результаты без тюнинга весов.

**Статус:** де-факто стандарт в 2025. Рекомендован HuggingFace, LangChain, Elasticsearch.
**Кто использует:** практически все production RAG-системы 2025.
**Наш проект:** ✅ уже реализован — BM25 + ChromaDB + RRF в `manager.py`.

### 4. Cross-Encoder Reranking — обязательный слой

Двухстадийный pipeline: bi-encoder initial retrieval (top-k=20–50) →
cross-encoder fine reranking (top-n=3–5). Убирает нерелевантные чанки перед генерацией.
Модели: ms-marco-MiniLM (быстрый CPU), BGE-reranker-v2-m3 (multilingual).

**Данные:** RankRAG pipelines показывают +7–8% MRR gains (arxiv 2506.00054).
**Наш проект:** ✅ уже реализован — `cross-encoder/ms-marco-MiniLM-L-6-v2` в `manager.py`.

### 5. Corrective RAG / Self-RAG — адаптивная генерация

**CRAG:** оценивает качество retrieved evidence перед генерацией, динамически решает —
продолжать, повторить retrieval или разбить на sub-queries.
**Self-RAG:** conditional retrieval с critique loops. +270% на factual QA (arxiv 2506.00054).

**Наш проект:** ✅ уже реализован — `grade_docs` (CRAG) + `route_or_retry` (Self-RAG, max 2 iter).

---

## На подходе, но ещё не production

| Метод | Статус | Почему интересен |
|-------|--------|-----------------|
| DeepSearch / iterative retrieval | Ранний продакшн (2026) | Агент сам делает N итераций поиска — Simon Willison называет «следующим поколением RAG» |
| Semantic chunking | Ранний продакшн | Разбивает по смыслу, не по N символам — лучше сохраняет контекст |
| Context Engineering | Концепция 2025–2026 | RAG как управление тремя источниками: domain knowledge + tools + conversation state |
| Graph-R1 | Research | Agentic GraphRAG через RL — агент traverses граф как environment (arxiv 2507.21892, июль 2025) |
| HyperRAG | Research | Гиперграфовое расширение GraphRAG, production данных пока нет |

---

## Что внедрить в RAG Support Assistant следующим

Три наиболее ценных улучшения для support-ticket RAG:

1. **HyDE (Hypothetical Document Embeddings)** — генерировать гипотетический ответ на вопрос,
   затем искать по его эмбеддингу вместо эмбеддинга вопроса. Хорошо работает когда вопросы
   короткие («Почему ошибка E20?»), а документы длинные. Реализация: 1 LLM-вызов в узле
   `transform_query`.

2. **Parent-Child Chunking** — хранить мелкие чанки для поиска, но подавать родительские
   параграфы в промпт. Код в `manager.py` (`ParentDocumentStore`) уже есть — нужно включить
   и протестировать на реальных данных поддержки.

3. **Semantic Chunking** — уже подготовлено (`RAG_SEMANTIC_CHUNKING=true`), нужно сравнить
   качество ответов с фиксированным chunking на своих данных. Ожидаемый эффект: меньше
   разрывов контекста в ответах.

---

## Источники

1. [Long Context vs. RAG — arxiv 2501.01880](https://arxiv.org/abs/2501.01880) — январь 2025
2. [RAGFlow: From RAG to Context](https://ragflow.io/blog/rag-review-2025-from-rag-to-context) — декабрь 2025
3. [Agentic RAG Survey — arxiv 2501.09136](https://arxiv.org/abs/2501.09136) — январь 2025
4. [RAG Architectures Survey — arxiv 2506.00054](https://arxiv.org/abs/2506.00054) — май 2025
5. [GraphRAG Survey — arxiv 2501.00309](https://arxiv.org/abs/2501.00309) — январь 2025
6. [Reranking Evolution — arxiv 2512.16236](https://arxiv.org/abs/2512.16236) — декабрь 2025
7. [Graph-R1 Agentic GraphRAG — arxiv 2507.21892](https://arxiv.org/abs/2507.21892) — июль 2025
8. [Simon Willison — DeepSearch, март 2025](https://simonwillison.net/2025/Mar/4/deepsearch-deepresearch/)
9. [Top 5 RAG Frameworks Nov 2025 — alphacorp.ai](https://alphacorp.ai/top-5-rag-frameworks-november-2025/)
10. [Hybrid Search & Reranking — Superlinked VectorHub](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
11. [RAG Market 2025–2035 — ResearchAndMarkets](https://www.businesswire.com/news/home/20251010008494/en/)
12. [Databricks — Long-Context RAG Performance](https://www.databricks.com/blog/long-context-rag-performance-llms)
