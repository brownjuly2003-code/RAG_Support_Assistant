import pytest
import sys
import os
from unittest.mock import Mock

# Добавляем корень проекта в PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from agent.graph import SupportAgentGraph  # type: ignore


class TestRetrieveNode:
    """
    Тесты для узла retrieve.

    Требование из задачи:
    - если retriever не вернул ни одного документа → context_docs должен быть пустым списком.
    """

    def setup_method(self):
        # Создаём граф и подменяем retriever на мок
        self.graph = SupportAgentGraph(vector_store=None)
        self.mock_retriever = Mock()
        # В реальном коде retriever, скорее всего, лежит как атрибут графа
        self.graph.retriever = self.mock_retriever  # type: ignore[attr-defined]

    def test_retrieve_with_documents_fills_context(self):
        """
        Позитивный сценарий: retriever возвращает документы → context_docs заполняется.
        """
        mock_docs = [
            Mock(page_content="Документ 1: гарантия", metadata={"source": "warranty.md"}, score=0.9),
            Mock(page_content="Документ 2: возврат", metadata={"source": "returns.md"}, score=0.8),
        ]
        self.mock_retriever.get_relevant_documents.return_value = mock_docs

        state = {
            "question": "Какая гарантия?",
            "trace_id": "trace_retrieve_1",
            "context_docs": [],
            "answer": None,
            "quality_score": None,
            "relevance_score": None,
            "route": None,
        }

        new_state = self.graph._retrieve_node(state)  # type: ignore[attr-defined]

        assert len(new_state["context_docs"]) == 2
        assert new_state["context_docs"][0]["content"] == "Документ 1: гарантия"
        assert new_state["context_docs"][0]["source"] == "warranty.md"

        self.mock_retriever.get_relevant_documents.assert_called_once_with("Какая гарантия?")

    def test_retrieve_no_documents_leaves_empty_context(self):
        """
        Основной негативный сценарий: retriever вернул пустой список → context_docs = [].
        """
        self.mock_retriever.get_relevant_documents.return_value = []

        state = {
            "question": "Вопрос, которого нет в базе",
            "trace_id": "trace_retrieve_2",
            "context_docs": [],
            "answer": None,
            "quality_score": None,
            "relevance_score": None,
            "route": None,
        }

        new_state = self.graph._retrieve_node(state)  # type: ignore[attr-defined]

        assert isinstance(new_state["context_docs"], list)
        assert new_state["context_docs"] == []

        self.mock_retriever.get_relevant_documents.assert_called_once_with("Вопрос, которого нет в базе")

    def test_retrieve_error_clears_context(self):
        """
        Если retriever выбрасывает исключение, узел должен:
        - не падать,
        - очистить context_docs (fail-safe поведение).
        """
        self.mock_retriever.get_relevant_documents.side_effect = Exception("Vector DB error")

        state = {
            "question": "Тестовый вопрос",
            "trace_id": "trace_retrieve_3",
            "context_docs": [{"content": "старый контент", "source": "old.md"}],
            "answer": None,
            "quality_score": None,
            "relevance_score": None,
            "route": None,
        }

        new_state = self.graph._retrieve_node(state)  # type: ignore[attr-defined]

        assert new_state["context_docs"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
