from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _clear_api_state, api_app


def test_ask_returns_429_after_60_requests(client: TestClient) -> None:
    for index in range(60):
        response = client.post(
            "/api/ask",
            json={"question": f"Тестовый вопрос {index}"},
        )
        assert response.status_code == 200

    response = client.post(
        "/api/ask",
        json={"question": "Запрос сверх лимита"},
    )

    assert response.status_code == 429


@pytest.mark.parametrize("storage_attr", ["storage", "_storage"])
def test_clear_api_state_resets_rate_limiter_storage_without_reset(
    monkeypatch: pytest.MonkeyPatch,
    storage_attr: str,
) -> None:
    limiter_storage = SimpleNamespace(**{storage_attr: {("ask", "testclient", 60): 3}})

    monkeypatch.setattr(api_app.app.state.limiter, "_storage", limiter_storage, raising=False)

    _clear_api_state()

    assert getattr(limiter_storage, storage_attr) == {}
