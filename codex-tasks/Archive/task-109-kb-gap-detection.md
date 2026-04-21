# Task 109 — KB gap detection: auto-ticket на "не знаю" кластеры

## Context
RQ-4 из plan. Когда бот отвечает "я не знаю / не нашёл информации" —
это сигнал что **KB неполный**. Сейчас эти ответы уходят в void:
пользователь уходит, операторы не узнают что "за неделю 15 человек
спросили про условия возврата а в KB нет документа".

## Goal
Детектить кластеры неотвеченных вопросов и создавать admin-ticket
"Дополнить KB по теме X (N запросов за 7 дней, примеры вопросов)".

## Files to change
- `graph.py` — generate/evaluate node помечает ответ флагом
  `knowledge_gap=True` если одно из:
  - Retrieved docs < 2 (ничего не нашли)
  - Faithfulness <0.5 (answer не опирается на docs)
  - LLM явно сказал "я не знаю" (regex / pattern match по ответу)
- `tracing/` — этот флаг пишется в trace
- `scripts/kb_gap_detector.py` — новый weekly job:
  1. Выбрать traces с `knowledge_gap=True` за 7 дней
  2. Кластеризовать вопросы по embedding (sklearn KMeans / HDBSCAN)
  3. Для каждого кластера ≥5 вопросов — создать `KnowledgeGap` запись
- `db/models.py` — таблица `KnowledgeGap` (cluster_id, topic_summary,
  sample_questions JSON, question_count, created_at, resolved_at)
- `alembic/versions/006_knowledge_gaps.py`
- `api/app.py` — `GET /api/admin/kb-gaps` для admin UI (role=admin)
- `static/admin.html` — секция "Knowledge gaps" со списком
- `tests/test_kb_gaps.py`

## Implementation sketch

### Gap detection (graph.py evaluate node)
```python
def _is_knowledge_gap(state) -> bool:
    if len(state.get("retrieved_docs", [])) < 2:
        return True
    quality = state.get("quality", {})
    if quality.get("faithfulness", 1.0) < 0.5:
        return True
    answer = state.get("answer", "").lower()
    gap_patterns = ["я не знаю", "не нашёл", "недостаточно информации",
                    "не могу ответить", "у меня нет данных"]
    if any(p in answer for p in gap_patterns):
        return True
    return False
```

### Clustering (scripts/kb_gap_detector.py)
```python
from sklearn.cluster import HDBSCAN
import numpy as np

embeddings = await embed_all(questions)  # existing embed function
clusterer = HDBSCAN(min_cluster_size=5, metric="cosine")
labels = clusterer.fit_predict(embeddings)

for cluster_id in set(labels):
    if cluster_id == -1:
        continue  # noise
    cluster_qs = [q for q, l in zip(questions, labels) if l == cluster_id]
    # Генерируем topic_summary через LLM: "Обобщи тему этих вопросов в 1 предложении"
    topic = await llm.generate(f"Суммируй тему: {cluster_qs[:10]}")
    await create_kb_gap(cluster_id, topic, cluster_qs, len(cluster_qs))
```

### Admin UI (static/admin.html)
Таблица:
| Topic | Count | Examples (expandable) | Actions |
| --- | --- | --- | --- |
| Условия возврата товара | 15 | "Как вернуть...", ... | [Mark resolved] [Export to docx] |

## CONSTRAINTS
- Clustering — ресурсоёмко. Cron weekly (не nightly). Helm CronJob
  `"0 3 * * 0"` (3 утра воскресенье)
- HDBSCAN на ≤1000 вопросов работает нормально, больше — нужна sampling
  стратегия (randomsample 500)
- tenant-scoped: gaps хранятся per tenant_id, admin видит только свой tenant
- Resolved gaps НЕ удаляются (audit trail), только флажок

## DONE WHEN
- [ ] Флаг `knowledge_gap` пишется в traces (проверить 3 сценария:
      нет docs, плохая faithfulness, explicit "не знаю")
- [ ] `python scripts/kb_gap_detector.py` на тестовых данных создаёт
      KnowledgeGap записи
- [ ] Admin UI показывает список gaps
- [ ] Миграция 006 прошла
- [ ] CronJob в Helm
- [ ] 245+ passed
- [ ] Commit: "KB gap detection: cluster unanswered questions into admin tickets (task-109)"
