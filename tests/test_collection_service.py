from __future__ import annotations

import asyncio
import inspect

import pytest

from service import collection_service as collection_service_module
from service.collection_service import CollectionService
from service.novel_service_errors import (
    CollectionApiError,
    CollectionBlockedError,
    CollectionHttpError,
    InvalidNovelInputError,
)


class RecordingRepository:
    def __init__(self) -> None:
        self.saved = None

    def save_collection(self, novel, statistics, author, episodes, comments) -> None:
        self.saved = (novel, statistics, author, episodes, comments)


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class FakeCrawler:
    headers = {"User-Agent": "test"}

    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    async def process_single_work(self, novel_id, session):
        self.calls.append((novel_id, session))
        return self.result


def session_factory(**kwargs):
    return FakeSession()


def success_result():
    collected_at = "2026-08-03T12:00:00+09:00"
    return {
        "type": "SUCCESS",
        "work": {
            "work_id": 123,
            "source_url": "https://www.munpia.com/novel/detail/123",
            "title": "수집 작품",
            "author_name": "수집 작가",
            "introduction": "소개",
            "free": False,
            "paid_serial": True,
            "adult": False,
            "view_count": 100,
            "preference_count": 20,
            "like_count": 3,
            "chapter_count": 2,
            "free_chapter_count": 1,
            "age_20s_percent": 25.5,
            "notice_count": 2,
            "created_at": "2026-01-01T00:00:00+09:00",
            "collected_at": collected_at,
        },
        "author": {
            "blogMemberId": 10,
            "authorName": "수집 작가",
            "blogUrl": "test-author",
        },
        "episodes": [
            {
                "episode_id": 101,
                "episode_number": 1,
                "episode_title": "무료",
                "access_type": "FREE",
                "collected_at": collected_at,
            },
            {
                "episode_id": 102,
                "episode_number": 2,
                "episode_title": "유료",
                "access_type": "PAID",
                "collected_at": collected_at,
            },
        ],
        "comments": [
            {
                "episode_id": 101,
                "comment_id": 201,
                "parent_comment_id": "",
                "reply_level": 0,
                "content_type": "TEXT",
                "comment_text": "댓글",
                "like_count": 1,
                "secret": False,
                "collected_at": collected_at,
            }
        ],
    }


@pytest.fixture
def work_556620_response():
    """실제 556620 단건 응답에서 서비스가 소비하는 필드 형태."""
    result = success_result()
    result["work"].update(
        {
            "work_id": 556620,
            "source_url": "https://novel.munpia.com/556620",
            "title": "내 훈수 한 번에 월클들의 고질병이 고쳐짐",
            "author_name": "솬스코",
            "chapter_count": 115,
        }
    )
    result["author"].update({"authorName": "솬스코"})
    return result


def make_service(result=None):
    repository = RecordingRepository()
    crawler = FakeCrawler(result or success_result())
    service = CollectionService(
        repository,
        crawler,
        session_factory=session_factory,
    )
    return service, repository, crawler


def test_parse_id_and_supported_urls() -> None:
    service, _, _ = make_service()
    assert service.parse_novel_id("123") == 123
    assert service.parse_novel_id("https://novel.munpia.com/123") == 123
    assert service.parse_novel_id("https://www.munpia.com/novel/detail/123") == 123


@pytest.mark.parametrize("value", ["", "0", "-1", "https://example.com/123"])
def test_parse_rejects_invalid_input(value) -> None:
    service, _, _ = make_service()
    with pytest.raises(InvalidNovelInputError):
        service.parse_novel_id(value)


def test_collect_calls_existing_single_work_and_adapts_entities() -> None:
    service, repository, crawler = make_service()
    result = asyncio.run(service.collect("123"))

    assert crawler.calls and crawler.calls[0][0] == 123
    assert result.novel.novel_id == 123
    assert result.novel.author_id == 10
    assert result.statistics.view_count == 100
    assert result.statistics.age_20s_percent == 25.5
    assert result.author.author_url == "https://library.munpia.com/test-author"
    assert [episode.access_type for episode in result.episodes] == ["FREE", "PAID"]
    assert result.comments[0].parent_comment_id is None
    assert repository.saved == (
        result.novel,
        result.statistics,
        result.author,
        result.episodes,
        result.comments,
    )


def test_actual_556620_response_shape_is_adapted(work_556620_response) -> None:
    service, repository, crawler = make_service(work_556620_response)

    result = asyncio.run(service.collect("https://novel.munpia.com/556620"))

    assert crawler.calls[0][0] == 556620
    assert result.novel.novel_id == 556620
    assert result.novel.title == "내 훈수 한 번에 월클들의 고질병이 고쳐짐"
    assert result.author.author_name == "솬스코"
    assert result.statistics.chapter_count == 115
    assert repository.saved is not None


@pytest.mark.parametrize("status", [403, 429])
def test_blocked_status_from_existing_crawler_is_translated(status) -> None:
    result = {
        "type": "FAIL",
        "log": {
            "http_status": status,
            "failure_type": f"HTTP_{status}_BLOCKED",
        },
    }
    service, repository, _ = make_service(result)
    with pytest.raises(CollectionBlockedError, match=str(status)):
        asyncio.run(service.collect("123"))
    assert repository.saved is None


def test_http_error_from_existing_crawler_is_translated() -> None:
    result = {
        "type": "FAIL",
        "log": {"http_status": 500, "failure_type": "HTTP_500"},
    }
    service, _, _ = make_service(result)
    with pytest.raises(CollectionHttpError, match="HTTP_500"):
        asyncio.run(service.collect("123"))


def test_api_error_from_existing_crawler_is_translated() -> None:
    result = {
        "type": "FAIL",
        "log": {"http_status": 200, "failure_type": "비공개 작품"},
    }
    service, repository, _ = make_service(result)
    with pytest.raises(CollectionApiError, match="비공개 작품"):
        asyncio.run(service.collect("123"))
    assert repository.saved is None


def test_service_reuses_crawler_without_batch_or_api_duplication() -> None:
    source = inspect.getsource(collection_service_module)
    assert ".process_single_work(" in source
    assert ".run(" not in source
    assert "OrderedCSVManager" not in source
    assert "/api/v1/" not in source
