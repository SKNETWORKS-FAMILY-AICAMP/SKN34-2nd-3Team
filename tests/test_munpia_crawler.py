from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from clawler.munpia_crawler import MunpiaAsyncCrawler


class FakeResponse:
    def __init__(self, status=200, payload=None, error=None):
        self.status = status
        self.payload = payload
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self):
        if self.error:
            raise self.error
        return self.payload


class FakeSession:
    def __init__(self, responder):
        self.responder = responder

    def get(self, url, **kwargs):
        response = self.responder(url, kwargs)
        if isinstance(response, BaseException):
            raise response
        return response


def ok(payload):
    return FakeResponse(payload={"code": "M000_00000", "result": payload})


def detail_payload(*, blog_url=""):
    return {
        "novelInfo": {"title": "작품", "genres": [], "tags": []},
        "blogUrl": blog_url,
        "noticeInfo": {"count": 0, "list": []},
        "events": [],
    }


def chapter(episode_id):
    return {"id": episode_id, "num": episode_id, "title": "회차", "free": True}


def page(url):
    return int(parse_qs(urlparse(url).query)["page"][0])


def run_crawl(responder):
    crawler = MunpiaAsyncCrawler(db_manager=None)
    return asyncio.run(crawler.process_single_work(556620, FakeSession(responder)))


def base_responder(url, _kwargs):
    if url.endswith("/read-statistics"):
        return ok({"maleCount": 1})
    if "/chapters?" in url:
        return ok({"list": []})
    if "/comments?" in url:
        return ok({"list": [], "totalPages": 1})
    return ok(detail_payload())


def test_second_episode_page_http_failure_discards_partial_entities():
    def responder(url, kwargs):
        if "/chapters?" in url:
            if page(url) == 2:
                return FakeResponse(status=503)
            return ok({"list": [chapter(i) for i in range(1, 101)]})
        return base_responder(url, kwargs)

    result = run_crawl(responder)

    assert result["type"] == "FAIL"
    assert result["log"]["http_status"] == 503
    assert result["log"]["failure_type"] == "EPISODES_PAGE_2_HTTP_503"
    assert "episodes" not in result


def test_middle_comment_page_api_failure_discards_partial_entities(monkeypatch):
    async def no_sleep(*_args):
        return None

    monkeypatch.setattr("clawler.munpia_crawler.asyncio.sleep", no_sleep)

    def responder(url, kwargs):
        if "/chapters?" in url:
            return ok({"list": [chapter(10)]})
        if "/comments?" in url:
            if page(url) == 2:
                return FakeResponse(payload={"code": "C999", "message": "댓글 오류"})
            return ok({"list": [{"id": 1, "parentId": 0}], "totalPages": 2})
        return base_responder(url, kwargs)

    result = run_crawl(responder)

    assert result["type"] == "FAIL"
    assert result["log"]["failure_type"] == "COMMENTS_EPISODE_10_PAGE_2_API_C999: 댓글 오류"
    assert "comments" not in result


@pytest.mark.parametrize(
    ("target", "response", "reason"),
    [
        ("statistics", TimeoutError("timed out"), "STATISTICS_NETWORK_ERROR: timed out"),
        ("episodes", FakeResponse(error=ValueError("bad json")), "EPISODES_PAGE_1_JSON_ERROR: bad json"),
        ("author", FakeResponse(error=ValueError("bad author json")), "AUTHOR_JSON_ERROR: bad author json"),
    ],
)
def test_timeout_and_json_errors_are_failures(target, response, reason):
    def responder(url, kwargs):
        if target == "author" and "library/info" not in url and not url.endswith("/read-statistics") and "/chapters?" not in url:
            return ok(detail_payload(blog_url="writer"))
        if target == "statistics" and url.endswith("/read-statistics"):
            return response
        if target == "episodes" and "/chapters?" in url:
            return response
        if target == "author" and "library/info" in url:
            return response
        return base_responder(url, kwargs)

    result = run_crawl(responder)

    assert result["type"] == "FAIL"
    assert result["log"]["failure_type"] == reason


def test_normal_empty_comments_remain_successful():
    def responder(url, kwargs):
        if "/chapters?" in url:
            return ok({"list": [chapter(10)]})
        return base_responder(url, kwargs)

    result = run_crawl(responder)

    assert result["type"] == "SUCCESS"
    assert len(result["episodes"]) == 1
    assert result["comments"] == []


def test_556620_success_path_keeps_115_episodes_and_1074_comments(monkeypatch):
    async def no_sleep(*_args):
        return None

    monkeypatch.setattr("clawler.munpia_crawler.asyncio.sleep", no_sleep)

    def responder(url, kwargs):
        if "/chapters?" in url:
            start = 1 if page(url) == 1 else 101
            end = 101 if page(url) == 1 else 116
            return ok({"list": [chapter(i) for i in range(start, end)]})
        if "/comments?" in url:
            episode_id = int(url.split("/entries/", 1)[1].split("/", 1)[0])
            if episode_id != 1:
                return ok({"list": [], "totalPages": 1})
            current_page = page(url)
            count = 100 if current_page <= 10 else 74
            offset = (current_page - 1) * 100
            return ok(
                {
                    "list": [
                        {"id": offset + i + 1, "parentId": 0}
                        for i in range(count)
                    ],
                    "totalPages": 11,
                }
            )
        return base_responder(url, kwargs)

    result = run_crawl(responder)

    assert result["type"] == "SUCCESS"
    assert len(result["episodes"]) == 115
    assert len(result["comments"]) == 1074
