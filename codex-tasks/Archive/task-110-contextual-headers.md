# Task 110 — Activate contextual headers в ingestion

## Context
FEAT-3 из plan. `add_contextual_headers()` функция упомянута в
`manager.py` и `graph.py` но по факту **не вызывается** в ingestion
pipeline — чанки попадают в ChromaDB без document-level context header.

Contextual headers (Anthropic "contextual retrieval" paper, Sep 2024):
перед каждым чанком добавляется 1-2 предложения описывающих место чанка
в документе ("Этот фрагмент из раздела 'Возврат товара' документа 'Политика
возврата 2024' описывает процесс ..."). Даёт +35-49% retrieval accuracy
на benchmarks.

## Goal
Включить contextual headers в ingestion pipeline под feature flag
`RAG_CONTEXTUAL_HEADERS` (default `true` — это proven улучшение).
Re-index existing KB по команде.

## Files to change
- `config/settings.py` — `contextual_headers: bool = env("RAG_CONTEXTUAL_HEADERS", default=True)`
- `ingestion/pipeline.py` — в chunk-generation loop, перед embedding,
  вызывать `add_contextual_headers(chunks, full_document)` если флаг ON
- `vectordb/manager.py` — убедиться что `add_contextual_headers()` корректно
  реализована: input (chunks, full_text) → output (chunks с prepended header)
- `scripts/reindex.py` — новый script: прогнать все существующие docs
  через обновлённый pipeline (админ команда, запускается вручную)
- `tests/test_ingestion_contextual.py` — test что чанки содержат header
  при флаге ON, не содержат при OFF

## Implementation sketch

### manager.py (add_contextual_headers)
```python
async def add_contextual_headers(chunks: list[Document],
                                  full_text: str,
                                  llm) -> list[Document]:
    """For each chunk, prepend a 1-2 sentence context header generated
    from the full document. Based on Anthropic contextual retrieval."""
    prompt_template = """Given the full document below, write 1-2 sentences
of context that situate this chunk within the document. Be concise.

<document>
{document}
</document>

<chunk>
{chunk}
</chunk>

Context:"""
    out = []
    for chunk in chunks:
        prompt = prompt_template.format(document=full_text[:4000], chunk=chunk.page_content)
        context = await llm.ainvoke(prompt)
        new_content = f"{context.strip()}\n\n{chunk.page_content}"
        out.append(Document(page_content=new_content, metadata={**chunk.metadata, "has_context_header": True}))
    return out
```

### scripts/reindex.py
```python
# Usage: python scripts/reindex.py --tenant TENANT_ID [--all]
# Читает existing ChromaDB metadata.source_doc_path, re-runs pipeline
```

### Cost consideration
Contextual headers = +1 LLM call per chunk при ingestion. Для 1000 чанков
= 1000 calls ≈ 3-5 минут на локальной Ollama. Приемлемо для init
ingestion, дорого для re-indexing. Поэтому:
- Для **new** uploads — всегда включено (дёшево, разовая операция)
- Для **reindex всего KB** — explicit command, прогресс-бар

## CONSTRAINTS
- Chunks должны remain под `chunk_size` limit — если header + content
  > limit, header приоритет, chunk truncate'нется с конца (logging warning)
- A/B тест: после reindex прогнать eval gate (RQ-2, task-108) — context_precision
  должен подрасти ≥5%. Если падает — откат флага
- Caching: если один full_text обрабатывается 10 раз (10 chunks из одного
  doc) — передавать summary, не full_text, после первого вызова (экономия)

## DONE WHEN
- [ ] `RAG_CONTEXTUAL_HEADERS=true` default в settings
- [ ] `add_contextual_headers` вызывается в ingestion/pipeline.py
- [ ] `python scripts/reindex.py` работает on test data
- [ ] A/B: до/после reindex, precision@5 подрос или same
- [ ] `has_context_header=True` в metadata новых chunks
- [ ] 248+ passed (3-5 новых test cases)
- [ ] Commit: "Activate contextual headers in ingestion pipeline (task-110)"
