from __future__ import annotations

from types import SimpleNamespace

import pytest

from service.novel_service import NovelService
from service.novel_service_errors import InvalidNovelInputError


class StubRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def _return(self, name: str, novel_id: int):
        self.calls.append((name, novel_id))
        return SimpleNamespace(novel_id=novel_id, kind=name)

    def get_novel(self, novel_id: int):
        return self._return("novel", novel_id)

    def get_novel_statistics(self, novel_id: int):
        return self._return("statistics", novel_id)

    def get_author(self, novel_id: int):
        return self._return("author", novel_id)

    def get_author_by_id(self, author_id: int):
        return self._return("author_by_id", author_id)

    def get_novels_by_author(self, author_id: int):
        return [self._return("novels_by_author", author_id)]

    def get_episodes(self, novel_id: int):
        return [self._return("episode", novel_id)]

    def get_comments(self, novel_id: int):
        return [self._return("comment", novel_id)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123", 123),
        ("https://www.munpia.com/novel/detail/456", 456),
        ("https://novel.munpia.com/789", 789),
    ],
)
def test_parse_novel_id(raw, expected):
    assert NovelService(StubRepository()).parse_novel_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "https://example.com/novel/1"])
def test_parse_rejects_invalid_input(raw):
    with pytest.raises(InvalidNovelInputError):
        NovelService(StubRepository()).parse_novel_id(raw)


@pytest.mark.parametrize(("raw", "expected"), [("1", 1), (" 42 ", 42)])
def test_parse_author_id(raw, expected):
    assert NovelService(StubRepository()).parse_author_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "0", "-1", "author"])
def test_parse_author_id_rejects_invalid_input(raw):
    with pytest.raises(InvalidNovelInputError):
        NovelService(StubRepository()).parse_author_id(raw)


def test_service_delegates_all_reads_to_repository():
    repository = StubRepository()
    service = NovelService(repository)

    assert service.get_novel(10).kind == "novel"
    assert service.get_novel_statistics(10).kind == "statistics"
    assert service.get_author(10).kind == "author"
    assert service.get_author_by_id(10).kind == "author_by_id"
    assert service.get_novels_by_author(10)[0].kind == "novels_by_author"
    assert service.get_episodes(10)[0].kind == "episode"
    assert service.get_comments(10)[0].kind == "comment"
    assert repository.calls == [
        ("novel", 10), ("statistics", 10), ("author", 10),
        ("author_by_id", 10), ("novels_by_author", 10),
        ("episode", 10), ("comment", 10),
    ]
