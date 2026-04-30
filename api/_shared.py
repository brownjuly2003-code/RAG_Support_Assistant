"""Shared lazy accessors for extracted API routers."""
from __future__ import annotations

from typing import Any


def app_module() -> Any:
    from api import app as _app  # noqa: PLC0415

    return _app
