def test_get_support_sink_importable() -> None:
    from mock_inbox import get_support_sink

    sink = get_support_sink()

    assert hasattr(sink, "send")
