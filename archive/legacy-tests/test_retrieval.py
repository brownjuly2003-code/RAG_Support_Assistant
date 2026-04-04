"""
demo/test_retrieval.py

Небольшой демо-скрипт для проверки связки:

- demo/seed_docs.py      — создаёт демо-документы (гарантия, возвраты, ошибки E20 и т.п.)
- ingestion/loader.py    — загружает документы в формат LangChain Document
- ingestion/chunking.py  — подбирает лучшую конфигурацию чанков
- vectordb/manager.py    — строит векторную БД и отдаёт retriever

Скрипт делает несколько тестовых запросов и показывает:

- какие фрагменты были найдены;
- для каких вопросов retrieval, по сути, "не нашёл ничего по делу".
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

# Добавляем корень проекта в PYTHONPATH, чтобы работали относительные импорты
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

# --- Импорты проектных модулей ---

from demo.seed_docs import seed_demo_docs  # noqa: E402
from ingestion.loader import load_documents_from_directory  # noqa: E402
from ingestion.chunking import find_best_chunking_config  # noqa: E402
from vectordb.manager import build_vector_store, get_retriever  # noqa: E402

# --- Эмбеддинги ---

def setup_embeddings():
    """
    Инициализация локальных эмбеддингов.

    Предпочтительный вариант — HuggingFaceEmbeddings / HuggingFaceEmbeddings из
    соответствующего интеграционного пакета LangChain, которые работают локально.

    Если нужный пакет не установлен, падаем обратно на FakeEmbeddings — это
    удобная заглушка: качество там ужасное, но демонстрация пайплайна работает.
    """
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore

        print("📦 Инициализирую локальные эмбеддинги HuggingFace...")
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/distiluse-base-multilingual-cased-v2"
        )
        print("✅ Эмбеддинги готовы\n")
        return embeddings
    except Exception as e:  # pragma: no cover - fallback
        print(f"⚠️ Не удалось инициализировать HuggingFaceEmbeddings: {e!r}")
        print("   Использую FakeEmbeddings (демо-режим, качество не гарантируется).")
        from langchain_core.embeddings import FakeEmbeddings  # type: ignore

        return FakeEmbeddings(model_name="fake", size=384)


# --- Утилиты для pretty-print ---

def _print_separator():
    print("\n" + "=" * 80 + "\n")


def _print_query_header(idx: int, query: str, expectation: str):
    print("-" * 80)
    print(f"Запрос #{idx}: {query}")
    print(f"Ожидание: {expectation}")
    print("-" * 80)


def _classify_relevance(query: str, text: str) -> bool:
    """
    Очень простая эвристика для определения "по делу / не по делу".

    Для PoC достаточно проверить наличие ключевых слов в тексте.
    В реальной системе это лучше делать по метаданным и более сложной логике.
    """
    q = query.lower()
    t = text.lower()

    if "ошибка e20" in q or "e20" in q:
        return "e20" in t
    if "гарант" in q:  # гарантия / гарантийные
        return "гарант" in t or "месяц" in t or "год" in t
    if "vpn" in q:
        return "vpn" in t
    return False


# --- Основной сценарий ---

def main() -> None:
    _print_separator()
    print("🚀 DEMO: тестирование retrieval-компоненты RAG-ассистента")
    _print_separator()

    # 1. Засеиваем демо-документы (если их ещё нет)
    seed_demo_docs(overwrite=False)
    docs_dir = Path(__file__).resolve().parent / "docs"
    print(f"Документы ожидаются в: {docs_dir}")

    # 2. Загружаем документы через ingestion.loader
    from langchain.schema import Document  # только для type hints/проверки
    docs: List[Document] = load_documents_from_directory(docs_dir)
    print(f"📄 Загружено документов: {len(docs)}")
    for d in docs:
        print(f"   - {d.metadata.get('file_name')} (source={d.metadata.get('source')})")

    if not docs:
        print("❌ Документов нет — прекращаем демо.")
        return

    _print_separator()

    # 3. Подбираем конфигурацию чанков через ingestion.chunking
    print("⚙️ Подбор оптимальной конфигурации чанков...")
    chunk_eval_result: Dict = find_best_chunking_config(docs, save_best=True)
    best_config = chunk_eval_result.get("best_config") or {
        "chunk_size": 800,
        "chunk_overlap": 200,
    }
    best_recall = chunk_eval_result.get("best_recall", 0.0)
    k_eval = chunk_eval_result.get("k", 3)

    print("Результаты оценки чанкинга:")
    for item in chunk_eval_result.get("results", []):
        cfg = item["config"]
        recall = item["recall"]
        print(
            f"  chunk_size={cfg['chunk_size']:4}, "
            f"overlap={cfg['chunk_overlap']:4} → Recall@{k_eval}={recall:.3f}"
        )

    print()
    print(f"👉 Выбрана конфигурация: {best_config} (Recall@{k_eval}={best_recall:.3f})")

    _print_separator()

    # 4. Инициализируем эмбеддинги и строим векторную БД
    embeddings = setup_embeddings()
    print("🔨 Строю векторную БД (Chroma по умолчанию, можно переключить через VECTOR_DB_TYPE)...")
    vector_store = build_vector_store(docs=docs, chunk_config=best_config, embeddings=embeddings)
    retriever = get_retriever(vector_store, k=6)
    print("✅ Векторная БД и retriever готовы.\n")

    _print_separator()

    # 5. Несколько тестовых запросов
    queries = [
        {
            "query": "Какая гарантия на ProLine?",
            "expectation": "Должен найти куски с гарантийными условиями (срок, месяцы/годы).",
        },
        {
            "query": "Что означает ошибка E20?",
            "expectation": "Должен найти описание ошибки E20 и рекомендации.",
        },
        {
            "query": "Есть ли у ProLine VPN-модуль?",
            "expectation": (
                "В демо-документах про VPN ничего нет → ожидаем, что retrieval "
                "не найдёт ничего по делу."
            ),
        },
    ]

    print("📋 Тестовые запросы к retriever:\n")

    for idx, item in enumerate(queries, start=1):
        query = item["query"]
        expectation = item["expectation"]

        _print_query_header(idx, query, expectation)

        try:
            results = retriever.get_relevant_documents(query)
        except AttributeError:
            # На случай, если retriever реализует .invoke(), а не .get_relevant_documents
            results = retriever.invoke(query)  # type: ignore

        if not results:
            print("❌ Retriever не вернул ни одного документа.")
            print("   → По сути, ничего по делу найти не удалось.\n")
            continue

        any_relevant = False

        for j, doc in enumerate(results, start=1):
            source = (doc.metadata or {}).get("source", "<unknown>")
            snippet = (doc.page_content or "").strip().replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:220] + "..."

            is_relevant = _classify_relevance(query, doc.page_content or "")
            mark = "✅ по делу" if is_relevant else "⚠️ мимо"

            print(f"[{j}] source={source} → {mark}")
            print(f"     {snippet}\n")

            if is_relevant:
                any_relevant = True

        if not any_relevant:
            print("➡️  В топ-k документов нет ни одного, который мы сочли бы релевантным.")
            print("    Формально retriever что-то вернул, но 'по делу' не нашёл.\n")

    _print_separator()
    print("🏁 Демо завершено.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:  # pragma: no cover
        print("\nОстановлено пользователем.")
