import pytest
import sys
import os
from unittest.mock import patch, Mock

# Добавляем корень проекта в PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from agent.graph import SupportAgentGraph  # type: ignore


class TestRouteNode:
    """
    Тесты для узла route в SupportAgentGraph.

    Предполагаемая логика маршрутизации:
    - если quality_score >= 80 и relevance_score >= 0.8 → route = "auto";
    - иначе → route = "human";
    - при "human" вызывается sink (эскалация), при "auto" — нет.
    """

    def setup_method(self):
        # В PoC граф может принимать готовый vector_store, для тестов он не нужен
        self.graph = SupportAgentGraph(vector_store=None)

    @pytest.mark.parametrize(
        "quality,relevance,expected_route",
        [
            (80, 0.8, "auto"),   # на пороге
            (90, 0.95, "auto"),  # высокие оценки
            (85, 0.9, "auto"),
        ],
    )
    def test_route_auto_high_scores(self, quality, relevance, expected_route):
        """
        При достаточно высоких quality и relevance узел должен выбирать 'auto'.
        """
        state = {
            "question": "Какая гарантия на продукт?",
            "trace_id": "trace_auto_1",
            "context_docs": [{"content": "текст", "source": "warranty.md"}],
            "answer": "Гарантия 24 месяца...",
            "quality_score": quality,
            "relevance_score": relevance,
            "route": None,
        }

        new_state = self.graph._route_node(state)  # type: ignore[attr-defined]

        assert new_state["route"] == expected_route

    @pytest.mark.parametrize(
        "quality,relevance,expected_route,reason",
        [
            (79, 0.8, "human", "quality чуть ниже порога"),
            (80, 0.79, "human", "relevance чуть ниже порога"),
            (60, 0.9, "human", "низкое качество"),
            (90, 0.6, "human", "низкая релевантность"),
            (50, 0.5, "human", "оба показателя низкие"),
        ],
    )
    def test_route_human_on_low_scores(self, quality, relevance, expected_route, reason):
        """
        При низких оценках узел должен эскалировать ('human').
        """
        state = {
            "question": "Сложный технический вопрос",
            "trace_id": "trace_human_1",
            "context_docs": [{"content": "текст", "source": "manual.md"}],
            "answer": "Неуверенный ответ",
            "quality_score": quality,
            "relevance_score": relevance,
            "route": None,
        }

        new_state = self.graph._route_node(state)  # type: ignore[attr-defined]

        assert new_state["route"] == expected_route, f"Ошибка: {reason}"

    def test_route_missing_scores_defaults_to_human(self):
        """
        Если оценки отсутствуют (None), узел должен безопасно эскалировать.
        """
        state = {
            "question": "Вопрос без оценки",
            "trace_id": "trace_human_2",
            "context_docs": [],
            "answer": "Ответ без оценки",
            "quality_score": None,
            "relevance_score": None,
            "route": None,
        }

        new_state = self.graph._route_node(state)  # type: ignore[attr-defined]

        assert new_state["route"] == "human"

    @patch("agent.graph.get_support_sink")
    def test_route_triggers_sink_on_human(self, mock_get_sink):
        """
        При маршруте 'human' граф должен вызвать sink.send(...) для эскалации.
        """
        mock_sink = Mock()
        mock_get_sink.return_value = mock_sink

        state = {
            "question": "Сложный вопрос",
            "trace_id": "trace_human_3",
            "context_docs": [],
            "answer": "Не знаю, как ответить",
            "quality_score": 60,
            "relevance_score": 0.6,
            "route": None,
        }

        new_state = self.graph._route_node(state)  # type: ignore[attr-defined]

        assert new_state["route"] == "human"
        mock_sink.send.assert_called_once()
        args, kwargs = mock_sink.send.call_args
        # entity_id должен содержать trace_id, а сообщение — вопрос
        assert state["trace_id"] in args[0]
        assert state["question"] in args[1]

    @patch("agent.graph.get_support_sink")
    def test_route_does_not_trigger_sink_on_auto(self, mock_get_sink):
        """
        При маршруте 'auto' sink не должен вызываться.
        """
        mock_sink = Mock()
        mock_get_sink.return_value = mock_sink

        state = {
            "question": "Простой вопрос",
            "trace_id": "trace_auto_2",
            "context_docs": [{"content": "текст", "source": "faq.md"}],
            "answer": "Уверенный ответ",
            "quality_score": 90,
            "relevance_score": 0.95,
            "route": None,
        }

        new_state = self.graph._route_node(state)  # type: ignore[attr-defined]

        assert new_state["route"] == "auto"
        mock_sink.send.assert_not_called()


if __name__ == "__main__":  # ручной запуск
    pytest.main([__file__, "-v"])
