"""PII redaction tests."""

from __future__ import annotations

import importlib
import logging
import sqlite3

from config.logging_config import PIIRedactionFilter
from utils.pii import contains_pii, redact_pii


def test_redact_email() -> None:
    assert "***@***.***" in redact_pii("Contact user@example.com for details")


def test_redact_phone() -> None:
    assert "+7-***" in redact_pii("Звоните +7 (999) 123-45-67")


def test_redact_card() -> None:
    assert "****-****" in redact_pii("Карта 1234 5678 9012 3456")


def test_no_pii() -> None:
    text = "Обычный текст без персональных данных"
    assert redact_pii(text) == text


def test_contains_pii() -> None:
    assert contains_pii("email: test@test.com")
    assert not contains_pii("just regular text")


def test_session_id_like_token_is_not_redacted() -> None:
    text = "session:ac82345678901ef"
    assert redact_pii(text) == text
    assert not contains_pii(text)


def test_logging_filter_redacts_message_args() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Contact %s",
        args=("user@example.com",),
        exc_info=None,
    )

    assert PIIRedactionFilter().filter(record) is True
    assert record.getMessage() == "Contact ***@***.***"


def test_trace_log_step_redacts_state_json(monkeypatch, tmp_path) -> None:
    trace_module = importlib.import_module("tracing.sqlite_trace")
    db_path = tmp_path / "traces.db"
    monkeypatch.setattr(trace_module._sqlite_trace, "_get_db_path", lambda: db_path)
    trace_module._sqlite_trace._init_db()

    trace_id = trace_module.start_trace()
    trace_module.log_step(
        trace_id,
        "node",
        {"email": "user@example.com", "text": "обычный текст"},
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT state_json FROM trace_steps WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()

    assert row is not None
    assert "***@***.***" in row[0]
    assert "user@example.com" not in row[0]
    assert "обычный текст" in row[0]
