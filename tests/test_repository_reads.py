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


def test_comment_sentiment_overview_counts_only_model_eligible_comments(
    monkeypatch,
):
    cursor = ReadCursor(row={})
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    repository.get_novel_comment_sentiment_overview(7)

    query, params = cursor.executed[0]
    assert "AS eligible_comment_count" in query
    assert "JOIN episode AS e ON e.episode_id = c.episode_id" in query
    assert "access_type = 'FREE'" in query
    assert "c.content_type = 'TEXT'" in query
    assert "c.reply_level = 0" in query
    assert "c.is_novel_author = FALSE" in query
    assert "TRIM(c.comment_text) <> ''" in query
    assert params == (7, 7, 7, 7)


def test_episode_sentiment_summaries_count_model_eligible_comments(monkeypatch):
    cursor = ReadCursor(rows=[])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    repository.get_episode_comment_sentiment_summaries(7)

    query, params = cursor.executed[0]
    assert "AS eligible_comment_count" in query
    assert "e.access_type = 'FREE'" in query
    assert "c.content_type = 'TEXT'" in query
    assert "c.reply_level = 0" in query
    assert "c.is_novel_author = FALSE" in query
    assert "TRIM(c.comment_text) <> ''" in query
    assert params == (7, 7, 7)


def test_episode_comment_list_reads_actual_commenter_fields(monkeypatch):
    cursor = ReadCursor(rows=[])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    repository.get_episode_comments_with_sentiment(11)

    query, params = cursor.executed[0]
    assert "c.commenter_nickname" in query
    assert "c.is_novel_author" in query
    assert "'' AS commenter_nickname" not in query
    assert "0 AS is_novel_author" not in query
    assert params == (11, 500)


def test_find_recommendations_returns_author_id_without_extra_lookup(monkeypatch):
    cursor = ReadCursor(rows=[])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    assert repository.find_recommendations_by_genre(3) == []

    query, params = cursor.executed[0]
    assert "n.novel_id, n.author_id, n.title" in query
    assert params == (3,)
    assert len(cursor.executed) == 1


def test_find_recommendations_without_genre_omits_only_genre_filter(monkeypatch):
    cursor = ReadCursor(rows=[])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    assert repository.find_recommendations_by_genre(None) == []

    query, params = cursor.executed[0]
    assert "JOIN novel_genre AS g ON g.genre_id = n.genre_1" in query
    assert "g.genre_id = %s" not in query
    assert "n.free = 1" in query
    assert "paid_serial, 0) = 0" in query
    assert "finish, 0) = 0" in query
    assert "pause, 0) = 0" in query
    assert "episode_number >= 30" in query
    assert "r.free_retention_score IS NOT NULL" in query
    assert params == ()


def test_find_recommendations_with_genre_preserves_parameter_contract(monkeypatch):
    cursor = ReadCursor(rows=[])
    repository = Repository()
    use_cursor(monkeypatch, repository, cursor)

    repository.find_recommendations_by_genre(3)

    query, params = cursor.executed[0]
    assert "n.genre_1 = %s" in query
    assert params == (3,)
