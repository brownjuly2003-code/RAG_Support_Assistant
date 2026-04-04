# Task 11 — Research: RAG evaluation metrics for production

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

## Research questions (заполни ответы ниже)

### Q1: Насколько надёжны keyword-based прокси?

Найди 1-2 научных работы или бенчмарка (2024-2025), сравнивающих keyword-overlap метрики
с LLM-судьями по корреляции с человеческой оценкой качества RAG.

**Ответ:**
```
[Correlation coefficient keyword vs LLM judge: ...]
[Conclusion: достаточно ли keyword proxies для support-ticket RAG или нет?]
[Source: ...]
```

---

### Q2: RAGAS package — что реально нужно для его запуска?

Официальный `ragas` пакет (https://github.com/explodinggradients/ragas):
- Нужен ли LLM-вызов на каждый evaluation run?
- Можно ли использовать локальную Ollama вместо OpenAI API?
- Примерная стоимость: сколько LLM-вызовов на 100 test cases?

**Ответ:**
```
[LLM calls per test case: ...]
[Ollama support: yes/no, how?]
[Alternative: ragas без LLM — возможно? ...]
[Source: docs.ragas.io или GitHub]
```

---

### Q3: Альтернативы RAGAS — DeepEval, TruLens, LangSmith

Для каждого фреймворка:
- Что умеет лучше RAGAS?
- Есть ли mode без LLM-вызовов (heuristic/embedding-based)?
- Подходит ли для multilingual (русский)?

**DeepEval:**
```
[Strengths vs RAGAS: ...]
[LLM-free mode: yes/no]
[Russian support: ...]
[Source: ...]
```

**TruLens:**
```
[Strengths: ...]
[LLM-free mode: yes/no]
[Production fit: ...]
[Source: ...]
```

**LangSmith:**
```
[Strengths: ...]
[Cost: ...]
[Fit for local/self-hosted: ...]
[Source: ...]
```

---

### Q4: Production-ready подход без per-query LLM overhead

Что используют в production support-ticket RAG системах (2024-2025)
когда не хотят тратить LLM-вызов на каждый вопрос для оценки?

Варианты для проверки:
- BERTScore / sentence-transformers cosine similarity (embedding-based, no LLM)
- SelfCheckGPT (sampling-based consistency check)
- Оффлайн-бенчмарк раз в неделю vs онлайн-оценка каждого ответа

**Ответ:**
```
[Рекомендуемый подход для production без per-query LLM: ...]
[Библиотека/инструмент: ...]
[Overhead (ms per request): ...]
[Source: ...]
```

---

### Q5: Метрики специфичные для support-ticket RAG

Что важнее для системы поддержки клиентов:
- Faithfulness (не галлюцинировать)?
- Answer completeness (дать полный ответ на вопрос)?
- Escalation accuracy (правильно решить авто vs human)?
- First-contact resolution rate (решил ли вопрос без повторного обращения)?

**Ответ:**
```
[Топ-3 метрики для support RAG по приоритету: ...]
[Как измерять escalation accuracy без ground truth? ...]
[Source: ...]
```

---

## Output: Recommendation

По итогам рисерча заполни:

```
РЕКОМЕНДАЦИЯ:
- Текущие keyword proxies: [оставить / заменить / дополнить] потому что [...]
- Добавить embedding-based метрику: [да/нет] — конкретно [модель/библиотека]
- RAGAS пакет: [использовать / не использовать] потому что [...]
- Для production monitoring: [...]
- Для offline benchmark: [...]
```

## CONSTRAINTS
- Только заполнить `[...]` в этом файле — никаких изменений в коде
- Сохранить файл как `docs/research/eval-metrics-2025.md`
- Никаких Python-файлов не трогать

## DONE WHEN
- [ ] `docs/research/eval-metrics-2025.md` существует
- [ ] Все `[...]` заполнены конкретными данными (не "N/A" или "TODO")
- [ ] Есть хотя бы 1 конкретная рекомендация по улучшению текущих метрик
