from fastapi.testclient import TestClient


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
