"""
integrations/mock_inbox.py

LocalFileSupportSink и выбор реализации SupportSink по ENV.

LocalFileSupportSink — это mock‑инбокс: вместо реального Bitrix
мы пишем эскалации в локальный JSONL‑файл:

    data/inbox/support_inbox.jsonl

Каждая строка в этом файле — отдельный JSON:

    {
      "entity_id": "trace-123",
      "question": "Вопрос пользователя...",
      "answer": "Автоответ бота...",
      "route": "human",
      "quality": 63,
      "relevance": 0.58,
      "ts": "2025-11-30T12:34:56.789Z"
    }

Это и есть наш "локальный аналог входящих комментариев":
  * удобно для PoC и локальной разработки,
  * не требует токенов и внешних сервисов,
  * легко прокидывается в простую веб‑панель или ноутбук для анализа.

Почему важно отделять Bitrix от mock‑инбокса через абстракцию?
----------------------------------------------------------------
И BitrixSupportSink, и LocalFileSupportSink реализуют один интерфейс
SupportSink. Графу не важно, какая реализация сейчас активна:

  * в DEV/PoC окружении SUPPORT_SINK_BACKEND=local →
    используем LocalFileSupportSink, всё работает локально;

  * в PROD окружении SUPPORT_SINK_BACKEND=bitrix →
    подключаем BitrixSupportSink, эскалации летят в CRM.

Бизнес‑логика графа, узел route и трассировка в SQLite при этом
не меняются. Меняется только конфигурация.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    from bitrix import SupportSink, BitrixSupportSink
except ImportError:
    from .bitrix import SupportSink, BitrixSupportSink

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    """Корень проекта относительно текущего файла."""
    return Path(__file__).resolve().parent


def _inbox_path() -> Path:
    """
    Путь к JSONL‑файлу mock‑инбокса:

        <project_root>/data/inbox/support_inbox.jsonl
    """
    root = _project_root()
    path = root / "data" / "inbox" / "support_inbox.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class LocalFileSupportSink(SupportSink):
    """
    Локальная реализация SupportSink.

    Вместо настоящей тикет‑системы мы просто дописываем строку JSON
    в support_inbox.jsonl. Это:
      * безопасно (нет внешних HTTP запросов),
      * прозрачно (файл можно открыть любым редактором),
      * удобно для демонстрации и отладки.
    """

    file_path: Path | None = None

    def __post_init__(self) -> None:
        if self.file_path is None:
            self.file_path = _inbox_path()

        if not self.file_path.exists():
            self.file_path.write_text("", encoding="utf-8")

    def send(self, entity_id: str, message: str) -> None:
        """
        Записывает эскалацию в JSONL‑файл.

        message:
          * в нашем графе это JSON‑строка с полями
            question / answer / route / quality / relevance / context_snippet;
          * если придёт обычный текст, мы тоже его сохраним, но часть полей
            останется пустой.
        """
        ts = datetime.now(timezone.utc).isoformat()

        try:
            base: Dict[str, Any] = json.loads(message)
            if not isinstance(base, dict):
                base = {"raw_message": message}
        except Exception:
            base = {"question": message}

        record: Dict[str, Any] = {
            "entity_id": entity_id,
            "question": base.get("question"),
            "answer": base.get("answer"),
            "route": base.get("route"),
            "quality": base.get("quality"),
            "relevance": base.get("relevance"),
            "ts": ts,
        }

        try:
            assert self.file_path is not None
            with self.file_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.exception("Не удалось записать сообщение в mock‑инбокс: %s", exc)


def get_support_sink() -> SupportSink:
    """
    Возвращает реализацию SupportSink по ENV.

    SUPPORT_SINK_BACKEND:
      * "bitrix" → BitrixSupportSink (настоящая интеграция)
      * "local"  → LocalFileSupportSink (mock‑инбокс, значение по умолчанию)
    """
    backend = os.getenv("SUPPORT_SINK_BACKEND", "local").strip().lower()

    if backend == "bitrix":
        logger.info("SupportSink backend: BitrixSupportSink")
        return BitrixSupportSink()

    logger.info("SupportSink backend: LocalFileSupportSink (по умолчанию)")
    return LocalFileSupportSink()
