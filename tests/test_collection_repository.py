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


def test_list_novels_selects_pause_for_collection_status(monkeypatch):
    class ListCursor(RecordingCursor):
        def fetchone(self):
            return {"total": 1}

        def fetchall(self):
            return [{"novel_id": 1, "pause": True}]

    connection = RecordingConnection()
    connection.cursor_instance = ListCursor()
    repository = Repository()
    monkeypatch.setattr(repository, "get_connection", lambda: connection)

    rows, total = repository.list_novels(page=1, page_size=20)

    assert total == 1
    assert rows == [{"novel_id": 1, "pause": True}]
    query, params = connection.cursor_instance.executed[1]
    assert "n.finish, n.pause" in query
    assert "n.paid_serial" not in query
    assert params == (0, 0, 0, 20, 0)


def test_list_genre_options_returns_schema_backed_names(monkeypatch):
    class GenreCursor(RecordingCursor):
        def fetchall(self):
            return [
                {"genre_id": 1, "genre_name": "판타지"},
                {"genre_id": 2, "genre_name": "무협"},
            ]

    connection = RecordingConnection()
    connection.cursor_instance = GenreCursor()
    repository = Repository()
    monkeypatch.setattr(repository, "get_connection", lambda: connection)

    options = repository.list_genre_options()

    assert options == [(1, "판타지"), (2, "무협")]
    query, params = connection.cursor_instance.executed[0]
    assert "FROM novel_genre" in query
    assert "genre_name IS NOT NULL" in query
    assert params == ()


def test_list_novels_applies_same_parameterized_filters_to_count_and_page(monkeypatch):
    class FilterCursor(RecordingCursor):
        def fetchone(self):
            return {"total": 1}

        def fetchall(self):
            return [{"novel_id": 7, "genre_1_name": "판타지", "genre_2_name": None}]

    connection = RecordingConnection()
    connection.cursor_instance = FilterCursor()
    repository = Repository()
    monkeypatch.setattr(repository, "get_connection", lambda: connection)

    rows, total = repository.list_novels(
        page=2,
        page_size=10,
        genre_id=3,
        serial_status="paused",
        min_view_count=100,
        min_preference_count=20,
        min_chapter_count=5,
    )

    assert total == 1
    assert rows[0]["genre_1_name"] == "판타지"
    count_query, count_params = connection.cursor_instance.executed[0]
    page_query, page_params = connection.cursor_instance.executed[1]
    for query in (count_query, page_query):
        assert "n.genre_1 = %s OR n.genre_2 = %s" in query
        assert "n.finish = 0 AND n.pause = 1" in query
        assert "COALESCE(s.view_count, 0) >= %s" in query
        assert "COALESCE(s.preference_count, 0) >= %s" in query
        assert "COALESCE(s.chapter_count, 0) >= %s" in query
    assert count_params == (3, 3, 100, 20, 5)
    assert page_params == (*count_params, 10, 10)
    assert "LEFT JOIN novel_genre AS g1 ON g1.genre_id = n.genre_1" in page_query
    assert "LEFT JOIN novel_genre AS g2 ON g2.genre_id = n.genre_2" in page_query


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("serializing", "n.finish = 0 AND n.pause = 0"),
        ("paused", "n.finish = 0 AND n.pause = 1"),
        ("finished", "n.finish = 1"),
        ("unknown", "n.finish IS NULL OR n.pause IS NULL"),
    ],
)
def test_list_novels_uses_only_schema_backed_serial_statuses(
    monkeypatch, status, expected
):
    class StatusCursor(RecordingCursor):
        def fetchone(self):
            return {"total": 0}

        def fetchall(self):
            return []

    connection = RecordingConnection()
    connection.cursor_instance = StatusCursor()
    repository = Repository()
    monkeypatch.setattr(repository, "get_connection", lambda: connection)

    repository.list_novels(page=1, page_size=20, serial_status=status)

    assert expected in connection.cursor_instance.executed[0][0]
