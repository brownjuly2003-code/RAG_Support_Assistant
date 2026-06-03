from fastapi.testclient import TestClient
from starlette.routing import Match

from auth.jwt_handler import create_access_token

AGENT_HEADERS = {"Authorization": f"Bearer {create_access_token('op1', 'agent')}"}
VIEWER_HEADERS = {"Authorization": f"Bearer {create_access_token('v1', 'viewer')}"}


def _route_endpoint_module(client: TestClient, path: str, method: str) -> str:
    for route in client.app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method not in getattr(route, "methods", set()):
            continue
        endpoint = route.endpoint
        while hasattr(endpoint, "__wrapped__"):
            endpoint = endpoint.__wrapped__
        return endpoint.__module__
    raise AssertionError(f"Route not found: {method} {path}")


def test_root_routes_are_owned_by_root_pages_router(client_with_key: TestClient) -> None:
    assert _route_endpoint_module(client_with_key, "/agent", "GET") == "api.routers.root_pages"
    assert _route_endpoint_module(client_with_key, "/admin/traces/{trace_id}", "GET") == "api.routers.root_pages"
    assert _route_endpoint_module(client_with_key, "/metrics", "GET") == "api.routers.root_pages"


def _registered_get_path(client: TestClient, path: str) -> bool:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    return any(
        route.matches(scope)[0] is Match.FULL
        for route in client.app.routes
        if hasattr(route, "matches")
    )


def test_admin_trace_root_redirect_requires_agent_or_admin(
    client_with_key: TestClient,
) -> None:
    unauthenticated = client_with_key.get(
        "/admin/traces/abc12345",
        follow_redirects=False,
    )
    viewer = client_with_key.get(
        "/admin/traces/abc12345",
        headers=VIEWER_HEADERS,
        follow_redirects=False,
    )

    assert unauthenticated.status_code == 401
    assert viewer.status_code == 403


def test_admin_trace_root_redirect_targets_registered_api_route(
    client_with_key: TestClient,
) -> None:
    response = client_with_key.get(
        "/admin/traces/abc12345",
        headers=AGENT_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/api/admin/traces/abc12345"
    assert _registered_get_path(client_with_key, response.headers["location"])
