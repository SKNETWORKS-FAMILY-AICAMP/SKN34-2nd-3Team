from __future__ import annotations

from contextlib import contextmanager

from repository.repository import Repository


class ReadCursor:
    def __init__(self, *, one=None, many=None) -> None:
        self.one = one
        self.many = many or []
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((" ".join(query.split()), tuple(params)))

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


def install_cursor(monkeypatch, repository, cursor):
    @contextmanager
    def fake_cursor(*, dictionary=False):
        assert dictionary is True
        yield cursor

    monkeypatch.setattr(repository, "_cursor", fake_cursor)


def test_get_author_by_id_queries_and_maps_entity(monkeypatch):
    repository = Repository()
    cursor = ReadCursor(
        one={
            "author_id": 7,
            "author_name": "테스트 작가",
            "author_url": "https://example.com/author/7",
            "is_illustrator": 0,
        }
    )
    install_cursor(monkeypatch, repository, cursor)

    author = repository.get_author_by_id(7)

    assert author.author_id == 7
    assert author.author_name == "테스트 작가"
    assert cursor.executed == [
        ("SELECT * FROM novel_author WHERE author_id = %s", (7,))
    ]


def test_get_novels_by_author_returns_every_mapped_novel(monkeypatch):
    repository = Repository()
    cursor = ReadCursor(
        many=[
            {
                "novel_id": 20,
                "source_url": "url-20",
                "title": "연재작",
                "author_id": 7,
            },
            {
                "novel_id": 10,
                "source_url": "url-10",
                "title": "완결작",
                "author_id": 7,
            },
        ]
    )
    install_cursor(monkeypatch, repository, cursor)

    novels = repository.get_novels_by_author(7)

    assert [novel.novel_id for novel in novels] == [20, 10]
    assert cursor.executed[0][1] == (7,)
    assert "WHERE author_id = %s" in cursor.executed[0][0]
    assert "ORDER BY finish, pause" in cursor.executed[0][0]
