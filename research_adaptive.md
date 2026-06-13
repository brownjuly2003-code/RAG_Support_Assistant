# Adaptive RAG, CRAG, и router-архитектуры RAG в 2024–июнь 2026

## Executive summary

За 2024–2026 годы вокруг RAG сложился отдельный саб-лейер: адаптивные роутеры, архитектурный search (RAISE, AutoRAG), и несколько серьёзных бенчмарков (CRAG, CRAG‑MM, RAGRouter‑Bench, LaRA).[^1][^2][^3][^4]

Ключевые тренды:
- **Adaptive / router‑first RAG**: лёгкие классификаторы и LLM‑роутеры, которые по запросу выбирают режим (LLM‑only, стандартный RAG, итеративный/graph RAG, long‑context) и даже конкретную модель.[^5][^6][^7][^8]
- **CRAG как де‑факто стандарт бенчмарка** для фактуального QA с mock‑API (web+KG), плюс мульти‑модальный CRAG‑MM для VLM‑ов.[^2][^9][^3][^10]
- **RAGRouter‑Bench** — отдельный бенчмарк именно для adaptive‑routing по query‑/corpus‑парадигмам (LLM‑only, Naive, Graph, Hybrid, Iterative) с явной метрикой cost‑vs‑quality.[^11][^12][^13][^1]
- **Contrastive / CRAG (Contrastive‑RAG)** — линия работ про контрастные объяснения и устойчивость к noisy контексту, orthogonal к чисто архитектурному routing.[^14][^15][^16]
- **RAISE/AutoRAG‑семейство** — формулировка дизайна RAG как задачи architecture search / HPO с единым search‑space и протоколами.[^8]

Практический вывод: в 2026 «best practice» для enterprise‑нагрузок — **router‑first гибридный RAG**: семантический роутер, гибридный retriever (BM25+vectors+RRF), селективный rerank, адаптивный выбор глубины цепочки и моделей, с eval‑ами уровня CRAG/RAGAS/LLM‑as‑judge.[^17][^6][^5]

***

## Бенчмарки RAG и adaptive‑routing (CRAG, CRAG‑MM, RAGRouter‑Bench, LaRA, RAISE)

### CRAG (Comprehensive RAG Benchmark)

CRAG — крупный factual QA‑бенчмарк (4 409 QA‑пар), имитирующий web и KG‑поиск через mock‑API, покрывающий 5 доменов и 8 типов вопросов, от попсовых сущностей до long‑tail и от статичных до сильно динамичных фактов.[^9][^18][^2]

Основные выводы CRAG:
- Продвинутые LLM‑ы без RAG дают ≤34 % accuracy, а «наивный» RAG поднимает это только до ~44 %.[^18][^2]
- Индустриальные RAG‑системы в лучшем случае отвечают без галлюцинаций ≈63 % вопросов, сильно хуже на динамичных, сложных или long‑tail фактах.[^2][^9]

Таким образом CRAG фиксирует потолок классического single‑pipeline RAG и мотивирует adaptive‑архитектуры и более умные evaluation‑метрики.

### CRAG‑MM и Meta CRAG‑MM Challenge

CRAG‑MM — расширение CRAG на мультимодальный multi‑turn VQA: около 5 000 изображений, 13 доменов, включая ~3 000 эгоцентрических кадров с wearable‑устройств.[^3][^10]

Meta CRAG‑MM Challenge использует этот датасет для соревнований по MM‑RAG с акцентом на dynamic multi‑turn диалог, multi‑source retrieval (web, KG) и query‑routing между каналами.[^10]

### RAGRouter‑Bench: бенчмарк для adaptive RAG routing

RAGRouter‑Bench моделирует **query–corpus compatibility** и даёт единый фреймворк для сравнения парадигм RAG: LLM‑only, NaiveRAG, GraphRAG, HybridRAG, IterativeRAG.[^12][^13][^1]

Характеристики:
- 7 727 запросов, 21 460 документов, 4 домена, аннотированные по 3 типам запросов: factual, reasoning, summarization.[^11][^12]
- Для каждой (query, corpus, method) фиксируется набор метрик качества, включая Semantic F1, Coverage и cost‑параметры.[^1][^12]

Ключевой эмпирический результат авторов: **HybridRAG** даёт «best balance» между quality и cost по большинству датасетов, особенно по Semantic F1 и Coverage, но ни одна парадигма не доминирует во всех комбинациях query–corpus.[^19][^12]

Отдельная работа «Lightweight Query Routing for Adaptive RAG» поверх RAGRouter‑Bench показывает, что простой TF‑IDF+SVM‑классификатор по тексту запроса достигает macro‑F1 ≈0.928 и accuracy ≈93.2 % при симуляции ≈28.1 % экономии токенов относительно всегда‑дорогого пути.[^11]

### LaRA: RAG vs long‑context routing

LaRA (ICML 2025) вводит бенчмарк для сравнения long‑context LLM‑ов и RAG по 2 326 тестам и 4 типам задач, фокусируясь на выборе между «скормить всё в контекст» и «делать retrieval».[^4]

Вывод: оптимальный выбор между LC и RAG зависит от комбинации возможностей модели, длины контекста, типа задачи и качества/характера retrieval; «one size fits all» стратегии нет, что прямо подталкивает к router‑архитектурам поверх LaRA‑подобных данных.[^4]

### RAISE: RAG design как architecture search

RAISE (RAG Intelligence Search Engine) формулирует дизайн RAG как задачу architecture search / HPO: общий search‑space включает query rewriting, chunking, retrieval, reranking, pruning, generation, с единой метрикой и бюджетом.[^8]

RAISE выступает как контролируемый бенчмарк для RAG‑HPO и сравнения AutoRAG‑подобных оптимизаторов, разделяя controller, search‑space и environment, и показывая, что преимущества adaptive‑оптимизаторов зависят от бюджета и структуры задачи.[^8]

***

## Adaptive RAG: идеи и практические реализации

### Концепт Adaptive RAG

Adaptive RAG в современной литературе — это обобщённый термин для систем, которые **динамически выбирают стратегию retrieval/генерации по запросу**, а не используют фиксированный RAG‑пайплайн.[^6][^20][^8]

Типичная реализация:
- Лёгкий query‑классификатор (логистическая регрессия, SVM, маленький трансформер) обучается на примерах запросов с метками режимов/сложности.[^6][^11]
- Каждый запрос роутится в один из нескольких пайплайнов: LLM‑only (без retrieval) для простых фактов, single‑step RAG для средней сложности, multi‑step / iterative / graph RAG для сложных reasoning/aggregation задач.[^1][^6]
- В более продвинутых вариантах: выбор модели‑генератора (разные LLM‑ы), варианта retriever (dense vs hybrid vs graph) и глубины цепочки инструментов.[^7][^5]

### Benchmarks и reported gains

Практические обзоры в 2026 отмечают Adaptive RAG как «emerging best practice» для mixed‑complexity production‑нагрузок, особенно для enterprise‑QA.[^5][^6]

Публичные цифры:
- В обзоре advanced‑RAG‑техник Adaptive RAG показал улучшение accuracy и эффективности на нескольких open‑domain QA‑датасетах против single‑step и iterative RAG; в частности, работа Yan et al. (NAACL 2024) демонстрирует значимый uplift по quality и снижению стоимости.[^6]
- Практический блог по Adaptive RAG (Postgres‑/hybrid‑ориентированный) показывает рост Precision@10 с 0.72 до 0.78, Recall@10 с 0.68 до 0.74 и nDCG@10 с 0.75 до 0.82 на Wikipedia‑корпусе при переходе от fixed hybrid к dynamic weighting, плюс прирост precision ~6–7 %, recall ~8 % и ощутимое ранжирование релевантных результатов выше.[^20]

В паре с RAGRouter‑Bench это задаёт хорошую основу для offline‑оценки Adaptive‑роутеров: можно сравнивать статические и адаптивные стратегии по trade‑off cost/quality.

### RAGRouter: LLM‑based routing между несколькими RAG‑LLM

RAGRouter (2025) формализует задачу routing между несколькими retrieval‑augmented LLM‑ами с учётом влияния retrieved‑документов, а не только parametric‑знаний модели.[^7]

Основная идея:
- Представить retrieved‑документы и «RAG‑capability embeddings» моделей и обучить роутер с contrastive learning, который для каждого запроса и контекста выбирает лучшую пару (LLM, retrieval‑setting).[^7]
- RAGRouter показывает, что учёт retrieved‑контента в роутинге превосходит методы, основанные только на статическом embedding‑пространстве моделей; на множестве knowledge‑intensive задач он обгоняет лучшую отдельную модель и существующие роутеры, при этом score‑threshold‑механизм даёт хороший баланс speed/quality под latency‑ограничениями.[^7]

### Enterprise Router‑First архитектуры (практика)

Практический reference‑архитектурный гайд 2026 года формулирует **Router‑First RAG** как стандарт: сначала семантический роутер, затем гибридный retriever (BM25+dense+RRF), затем опциональный cross‑encoder‑rerank, и только потом генерация.[^17][^5]

Ключевые элементы:
- Роутер классифицирует запросы в режимы Fast / Standard / Deep, в том числе отправляя часть в кеш или LLM‑only без retrieval для минимизации cost.[^5]
- Гибридный retriever с Reciprocal Rank Fusion как дефолт 2026 года, выигрывающий по relevance на Day‑1.[^17][^5]
- Cross‑encoder‑reranking включается только для сложных запросов, так как добавляет ~200 мс+ latency.[^5]
- Семантический кеш, guardrails (prompt‑injection detection, policy‑фильтры) и RAG‑eval (RAGAS‑подобные или LLM‑as‑judge) встроены в пайплайн.[^17][^5]

Эта архитектура практически совместима с идеями RAGRouter‑Bench и Adaptive RAG: роутер сначала выбирает класс запроса и глубину пайплайна, затем, при необходимости, специализированные retriever/генератор.

***

## CRAG / C‑RAG (Contrastive‑RAG) как метод и бенчмарк

### CRAG как бенчмарк (ещё раз кратко)

Как бенчмарк, CRAG уже описан выше: он задаёт референсную планку для factual QA‑RAG, особенно на динамичных и long‑tail фактах, и используется как основа KDD Cup 2024 и последующих соревнований.[^9][^18][^2]

В контексте routing он важен тем, что показывает: даже продвинутый single‑pipeline RAG даёт только ~44–63 % «надёжно корректных» ответов, оставляя огромный зазор для адаптивных и контрастивных методов.[^2][^9]

### Contrastive‑RAG (C‑RAG)

Contrastive‑RAG (NAACL 2024, arXiv:2410.22874) — framework, который улучшает критическое «чтение» контекста LLM‑ом через контрастные объяснения.[^15][^16][^14]

Pipeline C‑RAG:
- (i) стандартный retrieval по запросу, (ii) выбор и подача релевантных пассадов, (iii) генерация объяснений, которые **контрастно сравнивают релевантность** разных пассадов, и (iv) генерация финального ответа, опирающегося на эти объяснения.[^16][^15]
- Используются демонстрации от «teacher»‑LLM для обучения более мелких моделей быть устойчивыми к noisy контексту.[^16]

Результаты:
- C‑RAG улучшает SOTA RAG‑модели, требуя меньше prompt‑демонстраций и оставаясь устойчивым к perturbations в retrieved‑документах.[^15][^16]
- Показано, что примерно 1 000 примеров достаточны для обучения robustness к нерелевантному контексту без потери качества на нормальных примерах.[^16]

Практически C‑RAG хорошо сочетается с router‑архитектурой: роутер решает **куда** и **как глубоко** идти, а C‑RAG — **как читать контекст без галлюцинаций**.

***

## Key router‑архитектуры и паттерны 2024–2026

### Классификатор‑роутер (query‑complexity / query‑type routing)

Самый базовый паттерн — обучение классификатора, который по тексту запроса предсказывает тип (factual / reasoning / summarization / code / multi‑hop) и/или сложность, и на этой основе выбирает RAG‑вариант.[^1][^11][^6]

Примеры:
- RAGRouter‑Bench и работа по lightweight routing: TF‑IDF+SVM, MiniLM embeddings, hand‑crafted features; лучшая конфигурация TF‑IDF+SVM даёт macro‑F1 0.928 и accuracy 93.2 % на 7 727 запросах.[^11]
- Adaptive RAG тут же: маленький classifier решает, нужен ли retrieval и сколько шагов, часто вместе с оценкой confidence и fallback‑логикой.[^20][^6]

### LLM‑router с учётом retrieved контента

Следующий уровень — использовать LLM (либо отдельный router‑head) для более сложного routing, учитывающего retrieved‑контекст:
- RAGRouter моделирует влияние retrieved‑документов и capability‑embeddings LLM‑ов, применяя contrastive learning для выбора лучшей модели‑кандидата; это routing **между несколькими RAG‑LLM‑ами**, а не только между режимами одного пайплайна.[^7]
- Документ‑aware routing также появляется в работах вроде RDR² (Retrieve‑DocumentRoute‑Read), где LLM‑router ходит по деревьям структуры документа, но это больше про навигацию внутри одного корпуса.[^21]

### Router‑First hybrid search + rerank

Паттерн 2026 года для production:
- Шаг 1: semantic router → класс запроса, выбор пути: cache hit / LLM‑only / стандартный гибридный RAG / deep‑pipeline (tools, multi‑step, chain‑of‑thought).[^5][^17]
- Шаг 2: гибридный retriever с RRF, в т.ч. adaptive balancing dense vs sparse (Adaptive RAG).[^20][^17][^5]
- Шаг 3: (опционально) cross‑encoder‑rerank для top‑N, включаемый по сигналу роутера (сложность/неуверенность).[^5]
- Шаг 4: генерация + C‑RAG‑подобные техники для устойчивости к шуму.

### Architecture‑/Hyper‑parameter‑search‑router (RAISE, AutoRAG)

RAISE и родственные AutoRAG/AutoRAG‑HP систематизируют выбор конфигурации RAG не только по query, но и как offline‑оптимизацию: контроллер (RL/Bayesian/BO) пробегает по search‑space и учится выбирать near‑optimal конфигурации под заданный бюджет.[^8]

Такой контроллер можно интерпретировать как **meta‑router**, который учится offline и потом частично переносится в online‑routing (например, через эвристики и rule‑based policy, основанные на найденных паттернах).

***

## Метрики и бенчмаркинг router‑архитектур

### Метрики качества ответов и retrieval

Современные работы и практические гайды рекомендуют разделять метрики retrieval и generation:
- Retrieval: Context recall (попадание релевантного чанка в top‑K), context precision, MRR, nDCG.[^22][^20][^17]
- Generation: factual consistency, hallucination rate, answer accuracy/EM/F1, LLM‑as‑judge‑метрики (faithfulness, grounding).[^9][^2][^17]

Блоги по Adaptive RAG и RAG‑eval подчёркивают важность nDCG@K как метрики, чувствительной к порядку релевантных документов, особенно для гибридных и adaptive‑retrievers.[^20][^17]

### Метрики routing‑слоя

С учётом RAGRouter‑Bench и работ по lightweight routing используются дополнительные метрики для самого роутера:
- Классические classification‑метрики: accuracy, macro‑F1 по классам query‑types / pipeline‑choices.[^1][^11]
- Cost‑aware metrics: относительная экономия токенов/latency при удержании или улучшении качества (например, 28.1 % токен‑saving на RAGRouter‑Bench для лучшего TF‑IDF+SVM роутера).[^11]
- AUROC/калибровка confidence для предсказания успеха retrieval/ответа (в т.ч. в исследованиях LLM‑retrievers).[^23]

### Бенчмарки и датасеты для оценки routing

Краткий обзор релевантных датасетов/бенчмарков с точки зрения router‑архитектур:

| Бенчмарк | Фокус | Размер/домены | Relevance для router‑RAG |
|---------|-------|---------------|---------------------------|
| CRAG | Factual QA с web+KG mock‑API | 4 409 QA, 5 доменов, 8 типов вопросов | Оценка end‑to‑end RAG и влияния routing‑решений на factual accuracy / hallucinations. [^2][^18] |
| CRAG‑MM | Multimodal multi‑turn VQA | ~5 000 изображений, 13 доменов | Тестирование routing между vision‑, web‑ и KG‑каналами, особенно в multi‑turn режимах. [^3][^10] |
| RAGRouter‑Bench | Query–corpus–method совместимость | 7 727 запросов, 21 460 документов | Прямой бенчмарк для query‑side router‑ов между LLM‑only/Naive/Graph/Hybrid/Iterative RAG. [^1][^12][^11] |
| LaRA | RAG vs long‑context | 2 326 тестов, 4 задачи | Оценка router‑решений между LC‑и RAG‑подходами. [^4] |
| RAISE environments | RAG architecture search | Несколько датасетов, text+multimodal | Бенчмарк для meta‑router‑/контроллеров, выбирающих конфигурации пайплайна. [^8] |

***

## Практические рекомендации по дизайну Adaptive‑RAG / router‑систем (на июнь 2026)

На базе литературы и практических гайдов можно сформулировать набор практических паттернов для продакшн‑архитектуры.

### 1. Router‑first, hybrid‑retrieval‑by‑default

Рекомендуемый baseline для enterprise‑нагрузок:
- Вход → лёгкий semantic router оценивает тип/сложность/направление (QA vs генерация vs code‑assist) и пробрасывает сигналы downstream (например, нужен ли tools‑режим, сколько контекста, какой retriever).[^6][^5]
- Retriever по умолчанию гибридный (BM25/BM42 + dense) с RRF, со встроенным Adaptive‑RAG механизом изменения весов dense/sparse по типу запроса.[^17][^20][^5]
- Cross‑encoder‑rerank и/или Graph/Iterative‑режим включаются только по сигналу роутера (сложный reasoning, низкая confidence).[^1][^5]

### 2. Учёт стоимости: multi‑lane routing

С практической точки зрения полезно явно задизайнить несколько «полос» (lanes):
- **Cheap lane**: кеш / LLM‑only / очень ограниченный context‑window для FAQ‑/lookup‑запросов.[^6][^5]
- **Standard lane**: гибридный RAG (top‑K небольшое, без тяжёлого rerank).[^17][^5]
- **Heavy lane**: multi‑step/graph‑RAG, сложные tools, long‑context, cross‑encoder‑rerank; используется реже, но именно он даёт победу на сложных кейсах CRAG‑/LaRA‑типа.[^4][^1]

RAGRouter‑Bench и lightweight routing‑работы дают ориентиры по экономии: при хорошем роутере можно экономить ≈25–30 % токенов при сохранении качества относительно «всегда heavy lane».[^11]

### 3. Обучение роутера на реальных логах + бенчмарках

Хорошая практика — совмещать:
- Synthetic / public‑бенчмарки (CRAG, LaRA, RAGRouter‑Bench) для начального обучения/калибровки.[^12][^2][^4]
- Собственные логи запросов с разметкой: успех/фейл, потреблённые токены, latency, выбор конфигурации (retriever/LLM), чтобы обучать cost‑aware роутер.[^8][^20]

RAISE/AutoRAG‑подобные фреймворки можно использовать для offline‑HPO, а роутер — как способ переноса найденных конфигураций в online режим (через policy‑network или rule‑based mapping от фичей запроса/корпуса).

### 4. Обязательная оценка faithfulness / hallucination

CRAG и практические гайды подчёркивают, что рост retrieval‑метрик сам по себе не гарантирует меньше галлюцинаций; нужны отдельные метрики faithfulness и groundedness, часто на основе LLM‑as‑judge или специализированных систем (например, Future AGI evalы).[^2][^9][^17]

Для роутера важно отслеживать:
- В каких режимах и при каких признаках запросов растёт hallucination rate.
- Есть ли корреляция confidence‑сигналов роутера/retriever‑a с фактическим качеством ответов (AUROC).[^23]

### 5. Интеграция Contrastive‑/Self‑RAG техник в deep‑lane

Для тяжёлых режимов (multi‑hop, noisy corpora) имеет смысл включать C‑RAG или родственные техники:
- Контрастные объяснения помогают моделям «отфильтровать» нерелевантный контекст и давать grounded ответы, что критично для сложных CRAG‑/CRAG‑MM кейсов.[^14][^15][^16]
- Self‑RAG/Adaptive‑RAG‑подходы позволяют динамически решать, когда и что именно доизвлечь или переформулировать.[^6][^8]

***

## Заключение

Состояние на июнь 2026 такое: RAG сам по себе становится «commodity‑слоем», а реальный гейн в качестве и стоимости даёт **router‑/adaptive‑логика поверх него**, плюс продвинутые eval‑бенчмарки (CRAG, RAGRouter‑Bench, LaRA, RAISE).[^4][^2][^8][^1]

Для практических систем разумный путь — начинать с Router‑First hybrid RAG (semantic router → hybrid retrieval → selective rerank), валидировать на CRAG‑подобных задачах и постепенно добавлять adaptive weighting, multi‑lane routing и contrastive/self‑RAG методы там, где это реально улучшает trade‑off качество/стоимость/latency.[^20][^5][^17][^6]

---

## References

1. [A Dataset and Benchmark for Adaptive RAG Routing - arXiv](https://arxiv.org/abs/2602.00296) - In this work, we introduce RAGRouter-Bench, the first dataset and benchmark for adaptive RAG routing...

2. [[2406.04744] CRAG -- Comprehensive RAG Benchmark - arXiv](https://arxiv.org/abs/2406.04744) - Retrieval-Augmented Generation (RAG) has recently emerged as a promising solution to alleviate Large...

3. [CRAG-MM Multi-modal Multi-turn Comprehensive RAG Benchmark ...](https://github.com/facebookresearch/CRAG-MM) - CRAG-MM Multi-modal Multi-turn Comprehensive RAG Benchmark- dataset access- end-to-end evaluation- s...

4. [LaRA: Benchmarking Retrieval-Augmented Generation and Long ...](https://proceedings.mlr.press/v267/li25dv.html) - As Large Language Model (LLM) context windows expand, the necessity of Retrieval-Augmented Generatio...

5. [Enterprise RAG Blueprint: Router-First + Hybrid Search - stAI tuned](https://staituned.com/learn/midway/rag-reference-architecture-2026-router-first-design) - A pragmatic enterprise RAG architecture: semantic router lanes, hybrid retrieval with RRF, caching, ...

6. [12 Advanced RAG Techniques: Beyond Naive Retrieval [2026]](https://atlan.com/know/advanced-rag-techniques/) - Adaptive RAG trains a small, fast classifier on query examples to predict complexity. Each query is ...

7. [RAGRouter: Learning to Route Queries to Multiple Retrieval ... - arXiv](https://arxiv.org/abs/2505.23052) - Retrieval-Augmented Generation (RAG) significantly improves the performance of Large Language Models...

8. [RAISE: RAG Design as an Architecture Search Problem - arXiv](https://arxiv.org/html/2605.30029v1)

9. [CRAG: A Comprehensive RAG Benchmark - Emergent Mind](https://www.emergentmind.com/topics/comprehensive-rag-benchmark-crag) - CRAG is a dynamic, multi-domain benchmark that evaluates retrieval-augmented generation systems by c...

10. [Meta CRAG-MM Challenge](https://www.emergentmind.com/topics/meta-crag-mm-challenge) - The Meta CRAG-MM Challenge benchmarks multi-modal retrieval-augmented QA by evaluating VLMs on fact-...

11. [Lightweight Query Routing for Adaptive RAG: A Baseline Study on ...](https://www.catalyzex.com/paper/lightweight-query-routing-for-adaptive-rag-a) - Lightweight Query Routing for Adaptive RAG: A Baseline Study on RAGRouter-Bench: Paper and Code. Ret...

12. [ziqiwang0908/RAGRouter-Bench - GitHub](https://github.com/ziqiwang0908/RAGRouter-Bench) - RAGRouter-Bench is the first benchmark designed to evaluate Query-Corpus Compatibility in RAG system...

13. [RAGRouter-Bench: A Dataset and Benchmark for Adaptive RAG ...](https://arxiv.org/html/2602.00296v1)

14. [[Quick Review] Eliciting Critical Reasoning in Retrieval-Augmented ...](https://liner.com/review/eliciting-critical-reasoning-in-retrievalaugmented-language-models-via-contrastive-explanations) - Regarding this NAACL 2024 paper, this review summarizes Contrastive-RAG, a framework eliciting criti...

15. [Paper page - Eliciting Critical Reasoning in Retrieval-Augmented Language Models via Contrastive Explanations](https://huggingface.co/papers/2410.22874) - Join the discussion on this paper page

16. [[PDF] Eliciting Critical Reasoning in Retrieval-Augmented Language Models via Contrastive Explanations | Semantic Scholar](https://www.semanticscholar.org/paper/Eliciting-Critical-Reasoning-in-Retrieval-Augmented-Ranaldi-Valentino/b19d1070202c6fd84d0f0efa3fc63df8edf57e94) - This paper proposes Contrastive-RAG (C-RAG), a framework that retrieves relevant documents given a q...

17. [RAG LLM Explained 2026: Architecture, Eval, Hybrid Search](https://futureagi.com/blog/understanding-rag-llm-a-powerful-approach-for-ai-models/) - A 2026 Guide. Retrieval-Augmented Generation for LLMs in 2026: how it works, hybrid plus reranker st...

18. [CRAG - Comprehensive RAG Benchmark - OpenReview](https://openreview.net/forum?id=Q7lAqY41HH) - This paper introduces a novel dataset for retrieval-augmented generation (RAG), covering 5 domains a...

19. [Unifying Ranking and Generation in Query Auto-Completion via ...](https://fugumt.com/fugumt/paper_check/2602.01023v3_enmode)

20. [Adaptive RAG, understanding Confidence, Precision & nDCG](https://www.dbi-services.com/blog/rag-series-adaptive-rag-understanding-confidence-precision-ndcg/) - Adaptive RAG will allow us to talk about measuring the quality of the retrieved data and how we can ...

21. [Equipping Retrieval-Augmented Large Language Models ...](https://arxiv.org/html/2510.04293v1)

22. [[PDF] Evaluating Retrieval-Augmented Generation Architectures for Single ...](https://www.diva-portal.org/smash/get/diva2:2002498/FULLTEXT01.pdf) - This study further con- nects to work on multi-hop reasoning, where answers require combining eviden...

23. [Are LLM-Based Retrievers Worth Their Cost? An Empirical Study of ...](https://arxiv.org/html/2604.03676v1)
