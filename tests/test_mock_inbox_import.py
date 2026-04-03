import pytest


def test_get_support_sink_returns_object_with_send_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPPORT_SINK_BACKEND", "bitrix")

    from mock_inbox import get_support_sink

    sink = get_support_sink()

    assert hasattr(sink, "send")
