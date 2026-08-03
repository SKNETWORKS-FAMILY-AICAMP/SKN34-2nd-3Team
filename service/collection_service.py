from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import aiohttp

from clawler.munpia_crawler import MunpiaAsyncCrawler
from entity import Comment, Episode, Novel, NovelAuthor, NovelStatistics
from repository.collection_repository import CollectionRepository
from service.novel_service import NovelService
from service.novel_service_errors import (
    CollectionApiError,
    CollectionBlockedError,
    CollectionHttpError,
)


@dataclass(frozen=True, slots=True)
class CollectionResult:
    novel: Novel
    statistics: NovelStatistics
    author: NovelAuthor | None
    episodes: list[Episode]
    comments: list[Comment]


class CollectionService:
    """기존 문피아 단건 크롤러 결과를 Entity 저장 계약에 연결한다."""

    def __init__(
        self,
        repository: CollectionRepository,
        crawler: MunpiaAsyncCrawler | None = None,
        *,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
    ) -> None:
        self.repository = repository
        self.crawler = crawler or MunpiaAsyncCrawler(db_manager=None)
        self.session_factory = session_factory

    def parse_novel_id(self, url_or_id: str) -> int:
        return NovelService.parse_novel_id(self, url_or_id)

    def _validate_novel_id(self, novel_id: int) -> None:
        NovelService._validate_novel_id(self, novel_id)

    async def collect(self, url_or_id: str) -> CollectionResult:
        novel_id = self.parse_novel_id(url_or_id)
        stop_event = getattr(self.crawler, "stop_event", None)
        if stop_event is not None:
            stop_event.clear()
        timeout = aiohttp.ClientTimeout(total=30)
        async with self.session_factory(
            headers=self.crawler.headers,
            timeout=timeout,
        ) as session:
            raw_result = await self.crawler.process_single_work(novel_id, session)

        self._raise_for_failure(raw_result)
        result = self._to_collection_result(novel_id, raw_result)
        self.repository.save_collection(
            result.novel,
            result.statistics,
            result.author,
            result.episodes,
            result.comments,
        )
        return result

    def _raise_for_failure(self, result: dict[str, Any]) -> None:
        if result.get("type") == "SUCCESS":
            return
        log = result.get("log") if isinstance(result.get("log"), dict) else {}
        reason = str(log.get("failure_type") or "UNKNOWN_COLLECTION_ERROR")
        status = log.get("http_status")
        if status in {403, 429} or reason in {"HTTP_403_BLOCKED", "HTTP_429_BLOCKED"}:
            raise CollectionBlockedError(
                f"문피아가 수집 요청을 제한했습니다 ({reason})."
            )
        if status not in {None, "", 200}:
            raise CollectionHttpError(f"문피아 API 요청에 실패했습니다 ({reason}).")
        raise CollectionApiError(f"문피아 단건 수집에 실패했습니다: {reason}")

    def _to_collection_result(
        self, novel_id: int, result: dict[str, Any]
    ) -> CollectionResult:
        work = self._required_dict(result, "work")
        collected_at = self._required_datetime(work.get("collected_at"), "collected_at")
        author = self._author_to_entity(result.get("author"), work)
        novel = self._novel_to_entity(novel_id, work, author, collected_at)
        statistics = self._statistics_to_entity(novel_id, work, collected_at)
        episodes = [
            self._episode_to_entity(novel_id, row, collected_at)
            for row in self._required_list(result, "episodes")
        ]
        comments = [
            self._comment_to_entity(novel_id, row, collected_at)
            for row in self._required_list(result, "comments")
        ]
        return CollectionResult(novel, statistics, author, episodes, comments)

    def _novel_to_entity(
        self,
        novel_id: int,
        row: dict[str, Any],
        author: NovelAuthor | None,
        collected_at: datetime,
    ) -> Novel:
        title = self._optional_str(row.get("title"))
        source_url = self._optional_str(row.get("source_url"))
        if title is None or source_url is None:
            raise CollectionApiError("작품 제목 또는 주소가 비어 있습니다.")
        return Novel(
            novel_id=novel_id,
            source_url=source_url,
            title=title,
            introduction=self._optional_str(row.get("introduction")),
            author_id=author.author_id if author else None,
            origin_cover_url=self._optional_str(row.get("origin_cover_url")),
            free=self._optional_bool(row.get("free")),
            paid_serial=self._optional_bool(row.get("paid_serial")),
            exclusive=self._optional_bool(row.get("exclusive")),
            pre_exclusive=self._optional_bool(row.get("pre_exclusive")),
            adult=self._optional_bool(row.get("adult")),
            contest=self._optional_bool(row.get("contest")),
            rental=self._optional_bool(row.get("rental")),
            pause=self._optional_bool(row.get("pause")),
            finish=self._optional_bool(row.get("finish")),
            epub=self._optional_bool(row.get("epub")),
            ebook=self._optional_bool(row.get("ebook")),
            cp_novel=self._optional_bool(row.get("cp_novel")),
            created_at=self._optional_datetime(row.get("created_at")),
            updated_at=self._optional_datetime(row.get("updated_at")),
            paid_conversion_open_at=self._optional_datetime(
                row.get("paid_conversion_open_at")
            ),
            isbn=self._optional_str(row.get("isbn")),
            period=self._optional_int(row.get("period")),
            unit_type=self._optional_str(row.get("unit_type")),
            collected_at=collected_at,
        )

    def _statistics_to_entity(
        self, novel_id: int, row: dict[str, Any], collected_at: datetime
    ) -> NovelStatistics:
        return NovelStatistics(
            novel_id=novel_id,
            view_count=self._optional_int(row.get("view_count")),
            preference_count=self._optional_int(row.get("preference_count")),
            like_count=self._optional_int(row.get("like_count")),
            chapter_count=self._optional_int(row.get("chapter_count")),
            free_chapter_count=self._optional_int(row.get("free_chapter_count")),
            characters=self._optional_int(row.get("characters")),
            male_count=self._optional_int(row.get("male_count")),
            female_count=self._optional_int(row.get("female_count")),
            age_10s_percent=self._optional_float(row.get("age_10s_percent")),
            age_20s_percent=self._optional_float(row.get("age_20s_percent")),
            age_30s_percent=self._optional_float(row.get("age_30s_percent")),
            age_40s_percent=self._optional_float(row.get("age_40s_percent")),
            age_50s_percent=self._optional_float(row.get("age_50s_percent")),
            source_notice_count=self._optional_int(row.get("notice_count")),
            collected_at=collected_at,
        )

    def _author_to_entity(
        self, raw_author: Any, work: dict[str, Any]
    ) -> NovelAuthor | None:
        if not isinstance(raw_author, dict):
            return None
        author_id = self._optional_int(
            raw_author.get("blogMemberId") or raw_author.get("blogId")
        )
        author_name = self._optional_str(raw_author.get("authorName")) or self._optional_str(
            work.get("author_name")
        )
        if author_id is None or author_name is None:
            return None
        blog_url = self._optional_str(raw_author.get("blogUrl"))
        if blog_url and not blog_url.startswith(("http://", "https://")):
            blog_url = f"https://library.munpia.com/{blog_url.lstrip('/')}"
        return NovelAuthor(author_id, author_name, blog_url, False)

    def _episode_to_entity(
        self, novel_id: int, row: dict[str, Any], collected_at: datetime
    ) -> Episode:
        return Episode(
            episode_id=self._required_int(row.get("episode_id"), "회차 ID"),
            novel_id=novel_id,
            episode_number=self._required_int(row.get("episode_number"), "회차 번호"),
            episode_title=self._optional_str(row.get("episode_title")),
            published_at=self._optional_datetime(row.get("published_at")),
            access_type=self._optional_str(row.get("access_type")),
            view_count=self._optional_int(row.get("view_count")),
            like_count=self._optional_int(row.get("like_count")),
            comment_count=self._optional_int(row.get("comment_count")),
            page_count=self._optional_int(row.get("page_count")),
            adult=self._optional_bool(row.get("adult")),
            paid_conversion_before_entry=self._optional_bool(
                row.get("paid_conversion_before_entry")
            ),
            up=self._optional_bool(row.get("up")),
            collected_at=self._optional_datetime(row.get("collected_at")) or collected_at,
        )

    def _comment_to_entity(
        self, novel_id: int, row: dict[str, Any], collected_at: datetime
    ) -> Comment:
        return Comment(
            comment_id=self._required_int(row.get("comment_id"), "댓글 ID"),
            novel_id=novel_id,
            episode_id=self._required_int(row.get("episode_id"), "댓글 회차 ID"),
            parent_comment_id=self._optional_int(row.get("parent_comment_id")),
            reply_level=self._optional_int(row.get("reply_level")),
            content_type=self._optional_str(row.get("content_type")),
            comment_text=self._optional_str(row.get("comment_text")),
            like_count=self._optional_int(row.get("like_count")),
            dislike_count=self._optional_int(row.get("dislike_count")),
            created_at=self._optional_datetime(row.get("created_at")),
            secret=self._optional_bool(row.get("secret")),
            report_status=self._optional_str(row.get("report_status")),
            block_status=self._optional_bool(row.get("block_status")),
            collected_at=self._optional_datetime(row.get("collected_at")) or collected_at,
        )

    def _required_dict(self, data: dict[str, Any], key: str) -> dict[str, Any]:
        value = data.get(key)
        if not isinstance(value, dict):
            raise CollectionApiError(f"수집 결과에 {key}가 없습니다.")
        return value

    def _required_list(self, data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = data.get(key)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise CollectionApiError(f"수집 결과의 {key} 형식이 올바르지 않습니다.")
        return value

    def _required_int(self, value: Any, label: str) -> int:
        parsed = self._optional_int(value)
        if parsed is None:
            raise CollectionApiError(f"{label}가 비어 있습니다.")
        return parsed

    def _required_datetime(self, value: Any, label: str) -> datetime:
        parsed = self._optional_datetime(value)
        if parsed is None:
            raise CollectionApiError(f"{label}이 비어 있습니다.")
        return parsed

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError) as exc:
            raise CollectionApiError(f"정수 값 형식이 올바르지 않습니다: {value}") from exc

    def _optional_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise CollectionApiError(f"실수 값 형식이 올바르지 않습니다: {value}") from exc

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None

    def _optional_bool(self, value: Any) -> bool | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return value
        if value in {0, 1}:
            return bool(value)
        normalized = str(value).strip().lower()
        if normalized in {"true", "y", "yes"}:
            return True
        if normalized in {"false", "n", "no"}:
            return False
        raise CollectionApiError(f"boolean 값 형식이 올바르지 않습니다: {value}")

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise CollectionApiError(f"날짜 값 형식이 올바르지 않습니다: {value}") from exc
