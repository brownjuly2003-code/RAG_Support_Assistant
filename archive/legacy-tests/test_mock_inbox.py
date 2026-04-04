import pytest
import sys
import os
import json
import tempfile
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from integrations.mock_inbox import LocalFileSupportSink  # type: ignore


class TestLocalFileSupportSink:
    """
    Тесты для LocalFileSupportSink.

    Требование из задачи:
    - проверить запись в mock inbox (JSONL-файл).
    """

    def setup_method(self):
        # создаём временный файл для inbox, чтобы не трогать реальный
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        tmp.close()
        self.inbox_path = Path(tmp.name)
        self.sink = LocalFileSupportSink(file_path=str(self.inbox_path))

    def teardown_method(self):
        if self.inbox_path.exists():
            self.inbox_path.unlink()

    def test_send_writes_single_json_line(self):
        """
        Один вызов send(...) → в файле должна появиться одна корректная JSON-строка.
        """
        entity_id = "test_user_1"
        message = "Тестовая эскалация по гарантии"

        self.sink.send(entity_id, message)

        assert self.inbox_path.exists()

        lines = [line.strip() for line in self.inbox_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["entity_id"] == entity_id
        assert record["message"] == message
        # ts должен присутствовать, но конкретное значение не важно
        assert "ts" in record

    def test_multiple_sends_append_lines(self):
        """
        Несколько вызовов send(...) должны добавлять строки, а не перезаписывать файл.
        """
        messages = [
            ("user_1", "Сообщение 1"),
            ("user_2", "Сообщение 2"),
            ("user_3", "Сообщение 3"),
        ]

        for entity_id, msg in messages:
            self.sink.send(entity_id, msg)

        lines = [line.strip() for line in self.inbox_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == len(messages)

        parsed = [json.loads(line) for line in lines]
        for i, (entity_id, msg) in enumerate(messages):
            assert parsed[i]["entity_id"] == entity_id
            assert parsed[i]["message"] == msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
