from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token

api_app = importlib.import_module("api.app")


@pytest.fixture
def integration_api_app():
    return api_app


@pytest.fixture(autouse=True)
def _disable_vector_store_startup(monkeypatch: pytest.MonkeyPatch, integration_api_app) -> None:
    monkeypatch.setattr(integration_api_app, "initialize_vector_store", lambda: None)


@pytest.fixture
def integration_client(client_with_key: TestClient) -> TestClient:
    return client_with_key


@pytest.fixture
def integration_headers():
    def _make(tenant: str = "default", role: str = "admin") -> dict[str, str]:
        token = create_access_token("integration-user", role, tenant)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def integration_store() -> dict[str, object]:
    return {
        "docs": {},
        "sessions": {},
        "tickets": [],
    }


@pytest.fixture
def parse_sse_events():
    def _parse(payload: str) -> list[dict]:
        events: list[dict] = []
        for block in payload.split("\n\n"):
            if not block.strip():
                continue
            data_lines = [
                line.removeprefix("data: ")
                for line in block.splitlines()
                if line.startswith("data: ")
            ]
            if data_lines:
                events.append(json.loads("".join(data_lines)))
        return events

    return _parse
