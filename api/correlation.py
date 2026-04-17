"""Request-scoped correlation ID для логов и ответов."""
from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")

_current_request_id: ContextVar[Optional[str]] = ContextVar(
    "request_id", default=None
)


def generate_request_id() -> str:
    """UUID4 без дефисов."""
    return uuid.uuid4().hex


def sanitize_request_id(raw: Optional[str]) -> Optional[str]:
    """Проверить входящий X-Request-Id по строгому whitelist."""
    if not raw:
        return None
    if not _VALID_REQUEST_ID.fullmatch(raw):
        return None
    return raw


def get_request_id() -> Optional[str]:
    """Текущий request ID или None вне request-scope."""
    return _current_request_id.get()


def set_request_id(value: Optional[str]) -> None:
    """Установить request ID для текущего request-scope."""
    _current_request_id.set(value)
