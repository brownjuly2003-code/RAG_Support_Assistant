from fastapi.testclient import TestClient


def test_admin_html_served(client: TestClient) -> None:
    response = client.get("/static/admin.html")

    assert response.status_code == 200
    assert "RAG Support Assistant" in response.text
    assert "Circuit Breaker" in response.text
    assert "/static/admin.css" in response.text
    assert "/static/admin.js" in response.text


def test_admin_js_served(client: TestClient) -> None:
    response = client.get("/static/admin.js")

    assert response.status_code == 200
    assert "localStorage" in response.text
    assert "fetch(" in response.text
