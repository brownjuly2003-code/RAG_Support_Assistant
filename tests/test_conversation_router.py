from __future__ import annotations


def test_conversation_routes_live_in_subrouter() -> None:
    from api.routers import conversation

    route_paths = {getattr(route, "path", "") for route in conversation.router.routes}

    assert {"/ask", "/chat", "/ask/stream", "/chat/stream"}.issubset(route_paths)
