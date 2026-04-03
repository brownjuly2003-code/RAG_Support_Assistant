"""
config/logging_config.py

Настройка структурированного JSON-логирования для продакшн-окружения.
Вызвать setup_logging() один раз при старте приложения.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Форматирует лог-запись как однострочный JSON для stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z",
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }

        # Добавляем trace_id если передан через extra={"trace_id": ...}
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = trace_id

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """
    Инициализирует JSON-логирование на уровне root logger.

    Вызывать один раз при старте приложения:

        from config.logging_config import setup_logging
        setup_logging()

    После этого во всех модулях достаточно:

        import logging
        logger = logging.getLogger(__name__)
        logger.info("Сообщение", extra={"trace_id": "abc-123"})
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Не дублируем хэндлеры при повторных вызовах
    root.handlers.clear()
    root.addHandler(handler)

    # Подавляем лишний шум от библиотек
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
