from __future__ import annotations

import pytest

from repository.repository import Repository


class RecordingCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.executed.append((" ".join(query.split()), tuple(params)))

    def close(self):
        pass


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self, **kwargs):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def result(novel_id: int):
    return {
        "novel_author": [{"author_id": 1, "author_name": "작가"}],
        "novel_group": [], "novel_genre": [], "tag": [], "novel_tag": [],
        "novel": {"novel_id": novel_id, "title": "작품", "author_id": 1},
        "novel_statistics": {"novel_id": novel_id, "view_count": 10},
        "episode": [{"episode_id": 11, "novel_id": novel_id, "episode_number": 1}],
        "comment": [],
    }


def test_save_result_uses_one_db_transaction(monkeypatch):
    connection = RecordingConnection()
    repository = Repository()
    monkeypatch.setattr(repository, "get_connection", lambda: connection)

    changed = repository.save_result(1, result(1))

    assert connection.committed is True
    assert connection.rolled_back is False
    assert changed["novel"] == 1
    queries = [query for query, _ in connection.cursor_instance.executed]
    assert any("INSERT INTO `novel`" in query for query in queries)
    assert any("DELETE FROM episode" in query for query in queries)
    assert any("INSERT INTO `episode`" in query for query in queries)


def test_save_result_rejects_mismatched_novel_id():
    with pytest.raises(ValueError, match="novel_id"):
        Repository().save_result(1, result(2))
