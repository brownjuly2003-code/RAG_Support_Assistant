# Task 01 — Fix mock_inbox.py relative import

## Problem
`mock_inbox.py` line 53 uses `from .bitrix import SupportSink, BitrixSupportSink`.
This is a relative import that crashes when the file is imported as a top-level module
(e.g., from graph.py). `bitrix.py` lives in the same root directory.

## Fix — mock_inbox.py, line 53
Replace:
```python
from .bitrix import SupportSink, BitrixSupportSink
```
With:
```python
try:
    from bitrix import SupportSink, BitrixSupportSink
except ImportError:
    from .bitrix import SupportSink, BitrixSupportSink
```

## New test — tests/test_mock_inbox_import.py
```python
def test_get_support_sink_importable():
    from mock_inbox import get_support_sink
    sink = get_support_sink()
    assert hasattr(sink, "send")
```

## CONSTRAINTS
- Touch only: mock_inbox.py (1 line), tests/test_mock_inbox_import.py (new)
- Do NOT modify bitrix.py, graph.py, or any other file
- ruff check mock_inbox.py → 0 errors

## DONE WHEN
- [ ] `python -c "from mock_inbox import get_support_sink"` runs without error
- [ ] `pytest tests/test_mock_inbox_import.py -v` → 1 passed
