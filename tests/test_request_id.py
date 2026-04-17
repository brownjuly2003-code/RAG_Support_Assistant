"""Тесты correlation ID: генерация, сохранение, sanitize, в логах."""
from __future__ import annotations

import logging
import re

from fastapi.testclient import TestClient


def test_request_id_generated_when_header_absent(client: TestClient) -> None:
    resp = client.get("/api/health/live")
    assert "X-Request-Id" in resp.headers
    value = resp.headers["X-Request-Id"]
    assert re.fullmatch(r"[0-9a-f]{32}", value), value


def test_request_id_preserved_from_header(client: TestClient) -> None:
    incoming = "test-req-id-abc123"
    resp = client.get("/api/health/live", headers={"X-Request-Id": incoming})
    assert resp.headers["X-Request-Id"] == incoming


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    bad = "evil\nFAKE LOG LINE"
    resp = client.get("/api/health/live", headers={"X-Request-Id": bad})
    assert resp.headers["X-Request-Id"] != bad
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["X-Request-Id"])


def test_too_long_request_id_is_replaced(client: TestClient) -> None:
    bad = "a" * 200
    resp = client.get("/api/health/live", headers={"X-Request-Id": bad})
    assert resp.headers["X-Request-Id"] != bad


def test_request_id_appears_in_log_line(client: TestClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="api.app")
    incoming = "corr-0001"
    client.get("/api/health/live", headers={"X-Request-Id": incoming})

    matching = [record for record in caplog.records if incoming in record.getMessage()]
    assert matching, (
        f"expected log line to contain req_id={incoming}, "
        f"got:\n" + "\n".join(record.getMessage() for record in caplog.records)
    )
