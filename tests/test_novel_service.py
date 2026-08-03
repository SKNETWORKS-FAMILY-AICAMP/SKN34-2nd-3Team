from __future__ import annotations

import inspect

import pandas as pd
import pytest

from entity.comment import Comment
from entity.episode import Episode
from entity.novel import Novel
from entity.novel_author import NovelAuthor
from entity.novel_statistics import NovelStatistics
from repository.novel_repository import CsvNovelRepository
from service import novel_service as novel_service_module
from service.novel_service import NovelService
from service.novel_service_errors import (
    CsvSchemaError,
    InvalidNovelInputError,
)


EPISODE_COLUMNS_FOR_TEST = {
    "work_id",
    "episode_id",
    "episode_number",
    "episode_title",
    "published_at",
    "access_type",
    "view_count",
    "like_count",
    "comment_count",
    "page_count",
    "adult",
    "paid_conversion_before_entry",
    "up",
    "collected_at",
}

COMMENT_COLUMNS_FOR_TEST = {
    "work_id",
    "episode_id",
    "comment_id",
    "parent_comment_id",
    "reply_level",
    "content_type",
    "comment_text",
    "like_count",
    "dislike_count",
    "created_at",
    "secret",
    "report_status",
    "block_status",
    "collected_at",
}

AUTHOR_COLUMNS_FOR_TEST = {
    "author_id",
    "author_name",
    "author_url",
    "is_illustrator",
}


@pytest.fixture
def service(tmp_path) -> NovelService:
    works_path = tmp_path / "works.csv"
    authors_path = tmp_path / "authors.csv"
    episodes_path = tmp_path / "episodes.csv"
    comments_path = tmp_path / "comments.csv"

    works_data = [
        {
            "work_id": 123,
            "source_url": (
                "https://www.munpia.com/"
                "novel/detail/123"
            ),
            "title": "테스트 작품",
            "author_id": 10,
            "author_name": "테스트 작가",
            "illustrator_id": None,
            "illustrator_name": None,
            "introduction": "테스트 작품 소개",
            "cover_url": None,
            "origin_cover_url": None,
            "group_name": "일반연재",
            "genres_json": '["판타지"]',
            "tags_json": "[]",
            "genre_best_name": "판타지",
            "genre_best_code": "FANTASY",
            "free": True,
            "paid_serial": False,
            "exclusive": False,
            "pre_exclusive": False,
            "adult": False,
            "contest": False,
            "rental": False,
            "pause": False,
            "finish": False,
            "epub": False,
            "ebook": False,
            "cp_novel": False,
            "view_count": 1000,
            "preference_count": 100,
            "like_count": 50,
            "chapter_count": 2,
            "free_chapter_count": 2,
            "characters": 5000,
            "created_at": "2026-01-01T10:00:00",
            "updated_at": "2026-01-02T10:00:00",
            "paid_conversion_open_at": None,
            "isbn": None,
            "period": 0,
            "unit_type": "화",
            "male_count": 60,
            "female_count": 40,
            "age_10s_percent": 10,
            "age_20s_percent": 20,
            "age_30s_percent": 30,
            "age_40s_percent": 25,
            "age_50s_percent": 15,
            "notice_count": 1,
            "notices_json": "[]",
            "events_json": "[]",
            "collected_at": "2026-08-02T10:00:00",
        }
    ]

    authors_data = [
        {
            "author_id": 10,
            "author_name": "테스트 작가",
            "author_url": (
                "https://library.munpia.com/test-author"
            ),
            "is_illustrator": False,
        },
        {
            "author_id": 20,
            "author_name": "다른 작가",
            "author_url": (
                "https://library.munpia.com/other-author"
            ),
            "is_illustrator": False,
        },
    ]

    episodes_data = [
        {
            "work_id": 123,
            "episode_id": 1002,
            "episode_number": 2,
            "episode_title": "2화",
            "published_at": "2026-01-02T10:00:00",
            "access_type": "FREE",
            "view_count": 90,
            "like_count": 9,
            "comment_count": 0,
            "page_count": 11,
            "adult": False,
            "paid_conversion_before_entry": False,
            "up": False,
            "collected_at": "2026-08-02T10:00:00",
        },
        {
            "work_id": 123,
            "episode_id": 1001,
            "episode_number": 1,
            "episode_title": "1화",
            "published_at": "2026-01-01T10:00:00",
            "access_type": "FREE",
            "view_count": 100,
            "like_count": 10,
            "comment_count": 1,
            "page_count": 10,
            "adult": False,
            "paid_conversion_before_entry": False,
            "up": False,
            "collected_at": "2026-08-02T10:00:00",
        },
        {
            "work_id": 999,
            "episode_id": 9991,
            "episode_number": 1,
            "episode_title": "다른 작품",
            "published_at": "2026-01-01T10:00:00",
            "access_type": "FREE",
            "view_count": 1,
            "like_count": 0,
            "comment_count": 0,
            "page_count": 1,
            "adult": False,
            "paid_conversion_before_entry": False,
            "up": False,
            "collected_at": "2026-08-02T10:00:00",
        },
    ]

    comments_data = [
        {
            "work_id": 123,
            "episode_id": 1001,
            "comment_id": 2001,
            "parent_comment_id": None,
            "reply_level": 0,
            "content_type": "TEXT",
            "comment_text": "재미있어요",
            "like_count": 1,
            "dislike_count": 0,
            "created_at": "2026-01-01T11:00:00",
            "secret": False,
            "report_status": "NO",
            "block_status": False,
            "collected_at": "2026-08-02T10:00:00",
        },
        {
            "work_id": 999,
            "episode_id": 9991,
            "comment_id": 9992,
            "parent_comment_id": None,
            "reply_level": 0,
            "content_type": "TEXT",
            "comment_text": "다른 작품 댓글",
            "like_count": 0,
            "dislike_count": 0,
            "created_at": "2026-01-01T11:00:00",
            "secret": False,
            "report_status": "NO",
            "block_status": False,
            "collected_at": "2026-08-02T10:00:00",
        },
    ]

    pd.DataFrame(works_data).to_csv(
        works_path,
        index=False,
    )

    pd.DataFrame(authors_data).to_csv(
        authors_path,
        index=False,
    )

    pd.DataFrame(episodes_data).to_csv(
        episodes_path,
        index=False,
    )

    pd.DataFrame(comments_data).to_csv(
        comments_path,
        index=False,
    )

    repository = CsvNovelRepository(
        works_csv_path=works_path,
        authors_csv_path=authors_path,
        episodes_csv_path=episodes_path,
        comments_csv_path=comments_path,
        works_chunk_size=1,
        child_chunk_size=1,
    )

    return NovelService(repository=repository)


def test_parse_numeric_id(
    service: NovelService,
) -> None:
    assert service.parse_novel_id("123") == 123


def test_parse_legacy_munpia_url(
    service: NovelService,
) -> None:
    result = service.parse_novel_id(
        "https://novel.munpia.com/123"
    )

    assert result == 123


def test_parse_current_munpia_url(
    service: NovelService,
) -> None:
    result = service.parse_novel_id(
        "https://www.munpia.com/novel/detail/123"
    )

    assert result == 123


@pytest.mark.parametrize(
    "invalid_value",
    [
        "",
        " ",
        "0",
        "-1",
        "abc123",
        "https://example.com/123",
        "https://www.munpia.com/test/123",
    ],
)
def test_reject_invalid_input(
    service: NovelService,
    invalid_value: str,
) -> None:
    with pytest.raises(InvalidNovelInputError):
        service.parse_novel_id(invalid_value)


def test_get_novel_returns_entity(
    service: NovelService,
) -> None:
    novel = service.get_novel(123)

    assert isinstance(novel, Novel)
    assert novel.novel_id == 123
    assert novel.title == "테스트 작품"
    assert novel.author_id == 10
    assert novel.illustrator_id is None


def test_get_novel_statistics_returns_entity(
    service: NovelService,
) -> None:
    statistics = service.get_novel_statistics(123)

    assert isinstance(
        statistics,
        NovelStatistics,
    )
    assert statistics.novel_id == 123
    assert statistics.view_count == 1000
    assert statistics.preference_count == 100
    assert statistics.source_notice_count == 1


def test_get_author_returns_entity(
    service: NovelService,
) -> None:
    author = service.get_author(123)

    assert isinstance(author, NovelAuthor)
    assert author.author_id == 10
    assert author.author_name == "테스트 작가"
    assert author.author_url == (
        "https://library.munpia.com/test-author"
    )
    assert author.is_illustrator is False


def test_missing_author_returns_none(
    service: NovelService,
) -> None:
    assert service.get_author(777777) is None


def test_get_episodes_returns_only_target_novel(
    service: NovelService,
) -> None:
    episodes = service.get_episodes(123)

    assert len(episodes) == 2
    assert all(
        isinstance(episode, Episode)
        for episode in episodes
    )
    assert all(
        episode.novel_id == 123
        for episode in episodes
    )


def test_episodes_are_sorted_by_number(
    service: NovelService,
) -> None:
    episodes = service.get_episodes(123)

    assert [
        episode.episode_number
        for episode in episodes
    ] == [1, 2]


def test_get_comments_returns_only_target_novel(
    service: NovelService,
) -> None:
    comments = service.get_comments(123)

    assert len(comments) == 1

    comment = comments[0]

    assert isinstance(comment, Comment)
    assert comment.comment_id == 2001
    assert comment.novel_id == 123
    assert comment.episode_id == 1001
    assert comment.parent_comment_id is None
    assert comment.reply_level == 0
    assert comment.content_type == "TEXT"
    assert comment.comment_text == "재미있어요"
    assert comment.like_count == 1
    assert comment.dislike_count == 0
    assert comment.secret is False
    assert comment.report_status == "NO"
    assert comment.block_status is False
    assert comment.created_at is not None
    assert comment.collected_at is not None


def test_missing_novel_returns_none(
    service: NovelService,
) -> None:
    assert service.get_novel(777777) is None


def test_missing_statistics_returns_none(
    service: NovelService,
) -> None:
    assert (
        service.get_novel_statistics(777777)
        is None
    )


def test_missing_children_return_empty_lists(
    service: NovelService,
) -> None:
    assert service.get_episodes(777777) == []
    assert service.get_comments(777777) == []


def test_missing_required_column_raises_error(
    tmp_path,
) -> None:
    works_path = tmp_path / "works.csv"
    authors_path = tmp_path / "authors.csv"
    episodes_path = tmp_path / "episodes.csv"
    comments_path = tmp_path / "comments.csv"

    pd.DataFrame(
        [
            {
                "work_id": 123,
                # title 누락
                "source_url": "https://example.com",
            }
        ]
    ).to_csv(
        works_path,
        index=False,
    )

    pd.DataFrame(
        columns=sorted(AUTHOR_COLUMNS_FOR_TEST)
    ).to_csv(
        authors_path,
        index=False,
    )

    pd.DataFrame(
        columns=sorted(EPISODE_COLUMNS_FOR_TEST)
    ).to_csv(
        episodes_path,
        index=False,
    )

    pd.DataFrame(
        columns=sorted(COMMENT_COLUMNS_FOR_TEST)
    ).to_csv(
        comments_path,
        index=False,
    )

    repository = CsvNovelRepository(
        works_csv_path=works_path,
        authors_csv_path=authors_path,
        episodes_csv_path=episodes_path,
        comments_csv_path=comments_path,
    )
    broken_service = NovelService(repository=repository)

    with pytest.raises(CsvSchemaError):
        broken_service.get_novel(123)


def test_missing_author_column_raises_error(
    tmp_path,
) -> None:
    works_path = tmp_path / "works.csv"
    authors_path = tmp_path / "authors.csv"
    episodes_path = tmp_path / "episodes.csv"
    comments_path = tmp_path / "comments.csv"

    works_data = [
        {
            "work_id": 123,
            "source_url": (
                "https://www.munpia.com/"
                "novel/detail/123"
            ),
            "title": "테스트 작품",
            "introduction": None,
            "origin_cover_url": None,
            "author_id": 10,
            "free": True,
            "paid_serial": False,
            "exclusive": False,
            "pre_exclusive": False,
            "adult": False,
            "contest": False,
            "rental": False,
            "pause": False,
            "finish": False,
            "epub": False,
            "ebook": False,
            "cp_novel": False,
            "created_at": None,
            "updated_at": None,
            "paid_conversion_open_at": None,
            "isbn": None,
            "period": None,
            "unit_type": None,
            "collected_at": None,
        }
    ]

    pd.DataFrame(works_data).to_csv(
        works_path,
        index=False,
    )

    pd.DataFrame(
        [
            {
                "author_id": 10,
                # author_name 누락
                "author_url": None,
                "is_illustrator": False,
            }
        ]
    ).to_csv(
        authors_path,
        index=False,
    )

    pd.DataFrame(
        columns=sorted(EPISODE_COLUMNS_FOR_TEST)
    ).to_csv(
        episodes_path,
        index=False,
    )

    pd.DataFrame(
        columns=sorted(COMMENT_COLUMNS_FOR_TEST)
    ).to_csv(
        comments_path,
        index=False,
    )

    repository = CsvNovelRepository(
        works_csv_path=works_path,
        authors_csv_path=authors_path,
        episodes_csv_path=episodes_path,
        comments_csv_path=comments_path,
    )
    broken_service = NovelService(repository=repository)

    with pytest.raises(CsvSchemaError):
        broken_service.get_author(123)


def test_service_does_not_import_streamlit() -> None:
    source = inspect.getsource(
        novel_service_module
    )

    assert "import streamlit" not in source
