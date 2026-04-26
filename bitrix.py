"""
bitrix.py (root-level)

NOTE: Despite the legacy header, this file lives in the project root —
the `integrations/` package was never created. Imported as `from bitrix
import ...` from mock_inbox.py and config/settings.py.

Абстракция SupportSink и интеграция с Bitrix24.

Что такое эскалация?
--------------------
В RAG‑ассистенте поддержки не все запросы можно безопасно закрыть
автоматически. Когда модель:
  * даёт низкую оценку своему ответу,
  * не нашла достаточно контекста,
  * сталкивается с "тонкой" темой (деньги, договоры, блокировки),

мы не хотим молча вернуть сомнительный ответ. Вместо этого
вопрос поднимается на следующий уровень — к живому оператору поддержки.
Этот переход и называется "эскалация".

Зачем абстракция SupportSink?
------------------------------
Каналов эскалации может быть несколько:
  * Bitrix24 (боевой CRM / help‑desk),
  * локальный JSONL‑файл (mock‑инбокс для PoC),
  * почта, Jira, Telegram‑бот и т.д.

Чтобы граф не зависел от конкретного канала, мы описываем общий
интерфейс SupportSink с методом send(entity_id, message). Граф
знает только про этот метод, а не про детали REST API Bitrix.

Благодаря этому:
  * можно локально запускать PoC без Bitrix (используем mock‑инбокс);
  * в проде достаточно заменить реализацию sink'а;
  * проще писать тесты (можно подставить фейковый sink).
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class SupportSink(ABC):
    """
    Абстрактный приёмник эскалаций.

    Графу всё равно, куда именно пойдёт сообщение — в Bitrix, файл
    или ещё куда‑то. Он знает только, что у sink'а есть метод:

        send(entity_id: str, message: str) -> None
    """

    @abstractmethod
    def send(self, entity_id: str, message: str) -> None:
        """
        Отправить сообщение в систему поддержки.

        В happy‑path сценарии метод не должен прокидывать исключения
        наружу: в проде падение обработчика эскалации хуже, чем
        отсутствие комментария в Bitrix. Все ошибки логируем.
        """
        raise NotImplementedError


class BitrixSupportSink(SupportSink):
    """
    Реализация SupportSink для Bitrix24.

    Используем REST‑вебхук и метод crm.timeline.comment.add.
    Для простоты считаем, что переменная окружения BITRIX_WEBHOOK_URL
    уже содержит полный URL этого вебхука, например:

        https://example.bitrix24.ru/rest/1/XXXXXX/crm.timeline.comment.add.json

    Никаких токенов и ключей в коде — только ENV.
    """

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        self.webhook_url = webhook_url or os.getenv("BITRIX_WEBHOOK_URL")
        if not self.webhook_url:
            # Это не фатально: проект может работать с mock‑инбоксом.
            logger.warning(
                "BitrixSupportSink инициализирован без BITRIX_WEBHOOK_URL. "
                "Эскалации в Bitrix отправляться не будут."
            )

    def send(self, entity_id: str, message: str) -> None:
        """
        Отправляет комментарий в Bitrix, если вебхук настроен.

        Если ENV не заданы или запрос не удался — пишем в лог и
        идём дальше. Основной ответ пользователю уже сформирован,
        ломать флоу из‑за сбоя в интеграции нельзя.
        """
        if not self.webhook_url:
            logger.error(
                "Попытка отправки эскалации в Bitrix без BITRIX_WEBHOOK_URL. "
                "Сообщение не отправлено."
            )
            return

        payload = {
            "fields": {
                "ENTITY_ID": entity_id,
                # В реальном проекте сюда подставляют тип сущности
                # (DEAL / LEAD / CONTACT и т.п.). Для PoC достаточно
                # текстовой заглушки.
                "ENTITY_TYPE": "CRM_ENTITY",
                "COMMENT": message,
            }
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if not resp.ok:
                logger.error(
                    "Ошибка Bitrix при отправке эскалации: status=%s, body=%s",
                    resp.status_code,
                    resp.text,
                )
        except Exception as exc:
            logger.exception("Исключение при отправке эскалации в Bitrix: %s", exc)
