from __future__ import annotations

from contextlib import contextmanager

from repository.repository import Repository


class ReadCursor:
    def __init__(self, *, rows=None, row=None) -> None:
        self.rows = rows or []
        self.row = row
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.executed.append((" ".join(query.split()), tuple(params)))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


def use_cursor(monkeypatch, repository, cursor):
    @contextmanager
    def fake_cursor(*, dictionary=False):
        assert dictionary is True
        yield cursor

    monkeypatch.setattr(repository, "_cursor", fake_cursor)


def test_get_comments_reads_permanent_comment_table(monkeypatch):
    cursor = ReadCursor(rows=[{
        "comment_id": 3,
        "novel_id": 7,
        "episode_id": 11,
        "comment_text": "댓글",
    }])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    comments = repository.get_comments(7)

    query, params = cursor.executed[0]
    assert "SELECT * FROM comment WHERE novel_id = %s" in query
    assert "comment_import" not in query
    assert params == (7,)
    assert comments[0].comment_text == "댓글"


def test_get_primary_genre_name_joins_novel_primary_genre(monkeypatch):
    cursor = ReadCursor(row={"genre_name": "현대판타지"})
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    genre_name = repository.get_primary_genre_name(7)

    query, params = cursor.executed[0]
    assert "JOIN novel_genre AS g ON g.genre_id = n.genre_1" in query
    assert "WHERE n.novel_id = %s" in query
    assert params == (7,)
    assert genre_name == "현대판타지"


def test_get_primary_genre_name_returns_none_when_missing(monkeypatch):
    cursor = ReadCursor(row=None)
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    assert repository.get_primary_genre_name(7) is None


def test_find_recommendations_returns_author_id_without_extra_lookup(monkeypatch):
    cursor = ReadCursor(rows=[])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    assert repository.find_recommendations_by_genre(3, limit=12) == []

    query, params = cursor.executed[0]
    assert "n.novel_id, n.author_id, n.title" in query
    assert params == (3, 12)
    assert len(cursor.executed) == 1
