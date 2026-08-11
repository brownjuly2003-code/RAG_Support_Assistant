"""TraceService lifecycle ownership and compatibility contracts."""

from __future__ import annotations

from typing import Any

from tracing.service import TraceService


class _RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def start_trace(
        self,
        trace_id: str | None = None,
        tenant_id: str = "default",
        *,
        correlation_id: str | None = None,
    ) -> str:
        self.calls.append(("start", trace_id, tenant_id, correlation_id))
        return "internal-trace-id"

    def _state_to_dict(self, state: Any) -> dict[str, Any]:
        return dict(state)

    def log_step(self, trace_id: str, node_name: str, state: Any) -> None:
        self.calls.append(("log", trace_id, node_name, state))

    def finish_trace(self, trace_id: str, final_state: Any) -> None:
        self.calls.append(("finish", trace_id, final_state))


def test_trace_service_owns_start_log_finish_and_redacts() -> None:
    backend = _RecordingBackend()
    service = TraceService(
        backend,
        redact_text=lambda text: text.replace("user@example.com", "***@***.***"),
    )
    state = {"email": "user@example.com", "route": "auto"}

    trace_id = service.start_trace(
        trace_id="legacy-correlation",
        tenant_id="acme",
        correlation_id="legacy-correlation",
    )
    service.log_step(trace_id, "generate", state)
    service.finish_trace(trace_id, {"route": "auto"})

    assert trace_id == "internal-trace-id"
    assert backend.calls == [
        ("start", "legacy-correlation", "acme", "legacy-correlation"),
        (
            "log",
            "internal-trace-id",
            "generate",
            {"email": "***@***.***", "route": "auto"},
        ),
        ("finish", "internal-trace-id", {"route": "auto"}),
    ]
    assert state["email"] == "user@example.com"


def test_trace_service_preserves_backend_without_state_converter() -> None:
    class MinimalBackend:
        def __init__(self) -> None:
            self.logged: tuple[str, str, Any] | None = None

        def start_trace(
            self,
            trace_id: str | None = None,
            tenant_id: str = "default",
            *,
            correlation_id: str | None = None,
        ) -> str:
            return "trace"

        def log_step(self, trace_id: str, node_name: str, state: Any) -> None:
            self.logged = (trace_id, node_name, state)

        def finish_trace(self, trace_id: str, final_state: Any) -> None:
            return None

    backend = MinimalBackend()
    service = TraceService(backend)
    state = {"value": object()}

    service.log_step("trace", "node", state)

    assert backend.logged == ("trace", "node", state)


def test_sqlite_trace_lifecycle_functions_delegate_to_single_owner(monkeypatch) -> None:
    from tracing import sqlite_trace

    class RecordingService:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def start_trace(
            self,
            trace_id: str | None = None,
            tenant_id: str = "default",
            *,
            correlation_id: str | None = None,
        ) -> str:
            self.calls.append(("start", trace_id, tenant_id, correlation_id))
            return "owned-trace"

        def log_step(self, trace_id: str, node_name: str, state: Any) -> None:
            self.calls.append(("log", trace_id, node_name, state))

        def finish_trace(self, trace_id: str, final_state: Any) -> None:
            self.calls.append(("finish", trace_id, final_state))

    owner = RecordingService()
    monkeypatch.setattr(sqlite_trace, "trace_service", owner)

    trace_id = sqlite_trace.start_trace(correlation_id="request-1", tenant_id="acme")
    sqlite_trace.log_step(trace_id, "retrieve", {"documents": []})
    sqlite_trace.finish_trace(trace_id, {"route": "human"})

    assert owner.calls == [
        ("start", None, "acme", "request-1"),
        ("log", "owned-trace", "retrieve", {"documents": []}),
        ("finish", "owned-trace", {"route": "human"}),
    ]
