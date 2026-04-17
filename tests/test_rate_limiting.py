from fastapi.testclient import TestClient


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
