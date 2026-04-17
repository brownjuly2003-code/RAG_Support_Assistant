"""Telegram bot for RAG Support Assistant."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import logging  # noqa: E402

from config.settings import get_settings  # noqa: E402

logger = logging.getLogger(__name__)

_session_class: Any | None = None
_retriever: Any | None = None
_llm: Any | None = None
_sessions: dict[int, Any] = {}
_init_lock = asyncio.Lock()


async def _ensure_pipeline() -> None:
    global _session_class, _retriever, _llm

    if _session_class is not None and _retriever is not None and _llm is not None:
        return

    async with _init_lock:
        if _session_class is not None and _retriever is not None and _llm is not None:
            return

        try:
            from graph import ConversationSession, LocalOllamaLLM
        except ImportError:
            from agent.graph import ConversationSession, LocalOllamaLLM

        try:
            from manager import get_embeddings, get_retriever
        except ImportError:
            from vectordb.manager import get_embeddings, get_retriever

        try:
            from langchain_chroma import Chroma
        except ImportError as exc:
            raise RuntimeError("python package langchain-chroma is not installed") from exc

        settings = get_settings()
        chroma_dir = Path(settings.vectordb_chroma_dir)
        if not chroma_dir.exists() or not any(chroma_dir.iterdir()):
            raise RuntimeError(
                f"Vector store not found at {chroma_dir}. Upload documents before using the bot."
            )

        embeddings = get_embeddings()
        vector_store = Chroma(
            persist_directory=str(chroma_dir),
            embedding_function=embeddings,
            collection_name="documents",
        )

        _session_class = ConversationSession
        _retriever = get_retriever(vector_store, chunks=None)
        _llm = LocalOllamaLLM(model_name=settings.ollama_model_name)


async def _get_session(chat_id: int) -> Any:
    await _ensure_pipeline()

    if chat_id not in _sessions:
        settings = get_settings()
        _sessions[chat_id] = _session_class(
            retriever=_retriever,
            llm=_llm,
            max_iterations=settings.self_rag_max_iterations,
            max_history=20,
        )

    return _sessions[chat_id]


async def _ask_rag(chat_id: int, question: str) -> dict[str, Any]:
    session = await _get_session(chat_id)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, session.ask, question)


async def _answer_question(update: Any, question: str, usage_hint: bool = False) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    question = question.strip()
    if not question:
        text = "Использование: /ask <ваш вопрос>" if usage_hint else "Отправьте непустой вопрос."
        await message.reply_text(text)
        return

    if len(question) > 2000:
        await message.reply_text("Вопрос слишком длинный. Максимум: 2000 символов.")
        return

    await message.reply_text("Обрабатываю запрос...")

    try:
        result = await _ask_rag(chat.id, question)
        answer = (result.get("answer") or "Нет ответа").strip()
        quality = result.get("quality_score") or 50
        route = result.get("route") or "auto"
        docs = result.get("graded_docs") or result.get("context_docs") or []

        response_lines = [answer, "", f"Качество: {quality}/100 | Маршрут: {route}"]
        if docs:
            response_lines.extend(["", "Источники:"])
            for index, doc in enumerate(docs[:3], start=1):
                if isinstance(doc, dict):
                    metadata = doc.get("metadata", {}) or {}
                else:
                    metadata = getattr(doc, "metadata", {}) or {}
                source_name = metadata.get("source") or metadata.get("file_name") or "Неизвестно"
                response_lines.append(f"[{index}] {source_name}")

        await message.reply_text("\n".join(response_lines)[:4096])
    except Exception as exc:
        logger.error("Telegram RAG error: %s", exc, exc_info=True)
        await message.reply_text("Не удалось обработать запрос. Попробуйте позже.")


async def start_command(update: Any, context: Any) -> None:
    del context
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "RAG Support Assistant\n\n"
        "Задайте вопрос текстом или командой /ask <вопрос>"
    )


async def ask_command(update: Any, context: Any) -> None:
    question = " ".join(context.args) if getattr(context, "args", None) else ""
    await _answer_question(update, question, usage_hint=True)


async def message_handler(update: Any, context: Any) -> None:
    del context
    message = update.effective_message
    if message is None:
        return

    await _answer_question(update, message.text or "")


def run_bot(token: str) -> None:
    """Start Telegram bot."""
    try:
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
    except ImportError as exc:
        raise RuntimeError("python-telegram-bot is not installed") from exc

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        raise SystemExit(1)
    run_bot(settings.telegram_bot_token)
