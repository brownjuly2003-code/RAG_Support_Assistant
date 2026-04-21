from __future__ import annotations

import asyncio
import importlib

from fastapi import Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user
from auth.jwt_handler import create_access_token, create_refresh_token, verify_token

api_app = importlib.import_module("api.app")
graph_module = importlib.import_module("agent.graph")


def _auth_header(tenant: str = "default", role: str = "admin") -> dict[str, str]:
    token = create_access_token("u1", role, tenant)
    return {"Authorization": f"Bearer {token}"}


def test_jwt_tokens_encode_tenant() -> None:
    access_token = create_access_token("u1", "admin", "acme-corp")
    refresh_token = create_refresh_token("u1", "admin", "acme-corp")

    access_payload = verify_token(access_token, expected_type="access")
    refresh_payload = verify_token(refresh_token, expected_type="refresh")

    assert access_payload is not None
    assert refresh_payload is not None
    assert access_payload["tenant"] == "acme-corp"
    assert refresh_payload["tenant"] == "acme-corp"


def test_get_current_user_extracts_tenant_from_jwt() -> None:
    token = create_access_token("u1", "admin", "megacorp")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )

    user = get_current_user(request)

    assert user["tenant"] == "megacorp"


def test_context_var_set_by_middleware() -> None:
    from api.correlation import get_current_tenant, set_current_tenant

    captured: dict[str, str | None] = {}
    header = _auth_header("tenant-x")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", header["Authorization"].encode())],
        }
    )

    async def _call_next(_: Request) -> Response:
        captured["tenant"] = get_current_tenant()
        return Response(status_code=200)

    set_current_tenant(None)
    response = asyncio.run(api_app._tenant_context(request, _call_next))

    assert response.status_code == 200
    assert captured["tenant"] == "tenant-x"


def test_no_auth_defaults_to_default_tenant() -> None:
    from api.correlation import get_current_tenant, set_current_tenant

    captured: dict[str, str | None] = {}
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
    )

    async def _call_next(_: Request) -> Response:
        captured["tenant"] = get_current_tenant()
        return Response(status_code=200)

    set_current_tenant(None)
    response = asyncio.run(api_app._tenant_context(request, _call_next))

    assert response.status_code == 200
    assert captured["tenant"] == "default"


def test_run_qa_pipeline_passes_tenant_to_trace_and_state(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def _start_trace(trace_id=None, tenant_id="default") -> str:
        seen["tenant_id"] = tenant_id
        return trace_id or "trace-1"

    class FakeGraph:
        def invoke(self, state):
            seen["state"] = dict(state)
            return state

    monkeypatch.setattr(graph_module, "start_trace", _start_trace)
    monkeypatch.setattr(graph_module, "finish_trace", lambda trace_id, final_state: None)
    monkeypatch.setattr(graph_module, "build_support_graph", lambda **kwargs: FakeGraph())

    result = graph_module.run_qa_pipeline(
        question="?",
        retriever=object(),
        tenant_id="acme",
    )

    assert seen["tenant_id"] == "acme"
    assert seen["state"]["trace_id"] == "trace-1"
    assert seen["state"]["tenant_id"] == "acme"
    assert seen["state"]["max_iterations"] == 2
    assert result["tenant_id"] == "acme"


def test_ask_endpoint_propagates_tenant_to_graph(
    monkeypatch,
    client: TestClient,
) -> None:
    seen: dict[str, str] = {}

    def _spy_ask(question, trace_id=None, tenant_id="default"):
        _ = question, trace_id
        seen["tenant_id"] = tenant_id
        return {
            "answer": "ok",
            "quality_score": 90,
            "route": "auto",
            "trace_id": trace_id,
        }

    class FakeSession:
        ask = staticmethod(_spy_ask)
        _history: list = []

    monkeypatch.setattr(
        api_app,
        "_get_or_create_session",
        lambda sid: ("00000000-0000-0000-0000-000000000001", FakeSession()),
    )

    response = client.post(
        "/api/ask",
        json={"question": "?"},
        headers=_auth_header("acme-corp"),
    )

    assert response.status_code == 200
    assert seen["tenant_id"] == "acme-corp"
