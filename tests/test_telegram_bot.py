from __future__ import annotations

from types import SimpleNamespace

import pytest

from channels import telegram_bot


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


def _update(text: str | None = None, chat_id: int = 123):
    message = FakeMessage(text)
    return SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=chat_id),
    )


@pytest.mark.asyncio
async def test_start_command_replies_with_intro() -> None:
    update = _update()

    await telegram_bot.start_command(update, context=object())

    assert update.effective_message.replies == [
        "RAG Support Assistant\n\nЗадайте вопрос текстом или командой /ask <вопрос>"
    ]


@pytest.mark.asyncio
async def test_ask_command_without_args_returns_usage_hint() -> None:
    update = _update()
    context = SimpleNamespace(args=[])

    await telegram_bot.ask_command(update, context)

    assert update.effective_message.replies == ["Использование: /ask <ваш вопрос>"]


@pytest.mark.asyncio
async def test_answer_question_rejects_long_question() -> None:
    update = _update()

    await telegram_bot._answer_question(update, "x" * 2001)

    assert update.effective_message.replies == ["Вопрос слишком длинный. Максимум: 2000 символов."]


@pytest.mark.asyncio
async def test_message_handler_answers_with_sources(monkeypatch) -> None:
    async def fake_ask(chat_id: int, question: str):
        assert chat_id == 123
        assert question == "Where is my order?"
        return {
            "answer": "Check the order page.",
            "quality_score": 88,
            "route": "rag",
            "graded_docs": [
                {"metadata": {"source": "orders.md"}},
                SimpleNamespace(metadata={"file_name": "fallback.md"}),
            ],
        }

    monkeypatch.setattr(telegram_bot, "_ask_rag", fake_ask)
    update = _update("Where is my order?")

    await telegram_bot.message_handler(update, context=object())

    assert update.effective_message.replies[0] == "Обрабатываю запрос..."
    assert "Check the order page." in update.effective_message.replies[1]
    assert "Качество: 88/100 | Маршрут: rag" in update.effective_message.replies[1]
    assert "[1] orders.md" in update.effective_message.replies[1]
    assert "[2] fallback.md" in update.effective_message.replies[1]


@pytest.mark.asyncio
async def test_answer_question_reports_processing_errors(monkeypatch) -> None:
    async def broken_ask(chat_id: int, question: str):
        raise RuntimeError("backend down")

    monkeypatch.setattr(telegram_bot, "_ask_rag", broken_ask)
    update = _update("help")

    await telegram_bot._answer_question(update, "help")

    assert update.effective_message.replies == [
        "Обрабатываю запрос...",
        "Не удалось обработать запрос. Попробуйте позже.",
    ]


@pytest.mark.asyncio
async def test_get_session_reuses_session(monkeypatch) -> None:
    class FakeSession:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    async def fake_ensure_pipeline() -> None:
        telegram_bot._session_class = FakeSession
        telegram_bot._retriever = object()
        telegram_bot._llm = object()

    monkeypatch.setattr(telegram_bot, "_ensure_pipeline", fake_ensure_pipeline)
    telegram_bot._sessions.clear()

    first = await telegram_bot._get_session(5)
    second = await telegram_bot._get_session(5)

    assert first is second
    assert first.kwargs["max_history"] == 20


def test_run_bot_raises_when_dependency_missing(monkeypatch) -> None:
    real_import = telegram_bot.__import__ if hasattr(telegram_bot, "__import__") else __import__

    def fake_import(name, *args, **kwargs):
        if name == "telegram.ext":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="python-telegram-bot"):
        telegram_bot.run_bot("token")
