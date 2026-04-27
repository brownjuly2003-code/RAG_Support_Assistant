def test_get_support_sink_importable() -> None:
    from integrations.mock_inbox import get_support_sink

    sink = get_support_sink()

    assert hasattr(sink, "send")


def test_mock_inbox_project_root_resolves_to_repo_root() -> None:
    from pathlib import Path

    from integrations.mock_inbox import _project_root

    assert _project_root() == Path(__file__).resolve().parents[1]
