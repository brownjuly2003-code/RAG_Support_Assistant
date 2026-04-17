# Task 66 — MC-2: Telegram bot channel

## Goal
Добавить Telegram-бот как канал доступа к RAG.
`/ask <question>` → RAG pipeline → ответ в чат с sources.

## Files to create
- `channels/__init__.py`
- `channels/telegram_bot.py` — Telegram bot

## Files to change
- `requirements.txt` — добавить python-telegram-bot
- `config/settings.py` — `telegram_bot_token`
- `.env.example` — документация

---

## 1. requirements.txt

Добавить:
```
python-telegram-bot>=21.0
```

---

## 2. config/settings.py

Добавить:
```python
    # Telegram bot token (optional)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
```

---

## 3. channels/__init__.py

```python
"""Multi-channel support — Telegram, email, widget."""
```

---

## 4. channels/telegram_bot.py

```python
"""Telegram bot for RAG Support Assistant."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logger = logging.getLogger(__name__)


async def _ask_rag(question: str) -> dict:
    """Call RAG pipeline."""
    try:
        from graph import run_qa_pipeline
    except ImportError:
        from agent.graph import run_qa_pipeline

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_qa_pipeline, question)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "RAG Support Assistant\n\n"
        "Задайте вопрос текстом или командой /ask <вопрос>"
    )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text("Использование: /ask <ваш вопрос>")
        return

    await update.message.reply_text("Обрабатываю запрос...")

    try:
        result = await _ask_rag(question)
        answer = result.get("answer", "Нет ответа")
        quality = result.get("quality_score", 0)
        route = result.get("route", "auto")
        sources = result.get("sources", [])

        response = f"{answer}\n\n"
        if quality:
            response += f"Качество: {quality}/100 | Маршрут: {route}\n"
        if sources:
            response += "\nИсточники:\n"
            for i, src in enumerate(sources[:3], 1):
                source_name = src.get("source", "Неизвестно") if isinstance(src, dict) else str(src)
                response += f"  [{i}] {source_name}\n"

        await update.message.reply_text(response[:4096])  # Telegram limit
    except Exception as exc:
        logger.error("Telegram RAG error: %s", exc, exc_info=True)
        await update.message.reply_text(
            "Не удалось обработать запрос. Попробуйте позже."
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages as questions."""
    question = update.message.text
    if not question or len(question) > 2000:
        return
    context.args = question.split()
    await ask_command(update, context)


def run_bot(token: str) -> None:
    """Start Telegram bot (blocking)."""
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    from config.settings import get_settings
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        exit(1)
    run_bot(settings.telegram_bot_token)
```

---

## 5. .env.example

Добавить:
```
# Telegram bot token (from @BotFather). Leave empty to disable.
TELEGRAM_BOT_TOKEN=
```

---

## CONSTRAINTS
- Создать `channels/telegram_bot.py`
- Bot optional: без token — ничего не запускается
- Limit: ответ ≤4096 символов (Telegram limit)
- Input limit: question ≤2000 символов
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `channels/telegram_bot.py` создан
- [ ] `/start` → welcome message
- [ ] `/ask вопрос` → ответ + quality + sources
- [ ] Plain text → обработка как вопрос
- [ ] Без token: `python channels/telegram_bot.py` → error message, не crash
- [ ] `pytest tests/ -v` — проходит
