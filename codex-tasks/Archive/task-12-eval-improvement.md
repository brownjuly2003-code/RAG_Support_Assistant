# Task 12 — Improve evaluation metrics

## Goal
Улучшить `evaluation/ragas_eval.py`: добавить embedding-based similarity как дополнительную
метрику качества, не ломая существующий keyword-based pipeline.

## Prerequisite
Прочитай `docs/research/eval-metrics-2025.md` (результат task-11) перед началом.
Если файл не существует — остановись и напиши "BLOCKED: task-11 not done".

## Background: текущий код

`evaluation/ragas_eval.py` содержит:
- `faithfulness(answer, context_docs) -> float` — keyword overlap
- `answer_relevancy(question, answer) -> float` — keyword overlap
- `context_precision(question, context_docs, expected_keywords) -> float`
- `context_recall(context_docs, expected_keywords) -> float`
- `RAGEvaluator` класс с `evaluate_single()`, `evaluate_batch()`, `run_benchmark()`

**Слабое место:** `answer_relevancy` не улавливает синонимы.
Пример: вопрос «Как сбросить пароль?», ответ «Восстановление доступа выполняется через...»
→ keyword overlap = 0, но ответ релевантен.

## Changes

### 1. Добавить embedding-based answer_relevancy (файл: `evaluation/ragas_eval.py`)

После функции `answer_relevancy` добавить:

```python
def answer_relevancy_embedding(
    question: str,
    answer: str,
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
) -> float:
    """Semantic similarity between question and answer using sentence embeddings.

    Falls back to keyword-based answer_relevancy if sentence-transformers
    is not installed or encoding fails.

    Returns float in [0, 1].
    """
    if not question or not answer:
        return 0.0
    try:
        from sentence_transformers import SentenceTransformer, util  # noqa: PLC0415
        _model = SentenceTransformer(model_name)
        q_emb = _model.encode(question, convert_to_tensor=True)
        a_emb = _model.encode(answer, convert_to_tensor=True)
        score = float(util.cos_sim(q_emb, a_emb)[0][0])
        return max(0.0, min(1.0, score))
    except Exception:
        return answer_relevancy(question, answer)
```

### 2. Обновить `RAGEvaluator.evaluate_single()` (файл: `evaluation/ragas_eval.py`)

Добавить параметр `use_embeddings: bool = False` и использовать новую функцию:

```python
def evaluate_single(
    self,
    question: str,
    answer: str,
    context_docs: Any,
    expected_keywords: Optional[List[str]] = None,
    use_embeddings: bool = False,          # ← новый параметр
) -> Dict[str, float]:
```

Внутри метода заменить блок `answer_relevancy`:

```python
# Answer relevancy
if self._llm is not None:
    relevancy = _llm_answer_relevancy(question, answer, self._llm)
elif use_embeddings:
    relevancy = answer_relevancy_embedding(question, answer)
else:
    relevancy = answer_relevancy(question, answer)
```

### 3. Добавить `answer_relevancy_embedding` в `evaluate_batch` и `run_benchmark`

В `evaluate_batch` добавить параметр `use_embeddings: bool = False`
и передавать его в каждый вызов `evaluate_single`.

В `run_benchmark` — аналогично.

## CONSTRAINTS
- Изменить только `evaluation/ragas_eval.py`
- НЕ добавлять `sentence-transformers` в `requirements.txt` — зависимость уже есть
  (используется для BGE-M3 в vectordb/manager.py)
- Функция `answer_relevancy_embedding` должна gracefully деградировать на keyword fallback
- Все существующие тесты должны проходить без изменений (они не используют `use_embeddings=True`)
- Никаких других файлов не трогать

## DONE WHEN
- [ ] `evaluation/ragas_eval.py` содержит функцию `answer_relevancy_embedding`
- [ ] `RAGEvaluator.evaluate_single` принимает `use_embeddings: bool = False`
- [ ] При `use_embeddings=True` возвращает embedding-based score для answer_relevancy
- [ ] При отсутствии sentence-transformers — fallback на keyword overlap (не падает)
- [ ] `pytest tests/ -v` проходит
