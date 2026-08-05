from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from clawler.munpia_crawler import MunpiaAsyncCrawler
from repository.repository import Repository
from service.novel_service import NovelService
from service.novel_service_errors import (
    CollectionApiError,
    CollectionBlockedError,
    CollectionHttpError,
)


@dataclass(frozen=True, slots=True)
class CollectionResult:
    novel_id: int
    title: str
    change_type: str
    changed_rows: dict[str, int]


@dataclass(frozen=True, slots=True)
class CollectionProgress:
    event: str
    novel_id: int
    message: str
    elapsed_seconds: float
    phase: str = ""
    chapter_done: int = 0
    chapter_total: int | None = None
    chapter_in_flight: int = 0
    chapter_failed: int = 0
    result: CollectionResult | None = None


class CollectionService:
    def __init__(
        self,
        repository: Repository,
        *,
        crawler_factory: Callable[[], MunpiaAsyncCrawler] | None = None,
    ) -> None:
        self.repository = repository
        self.crawler_factory = crawler_factory or MunpiaAsyncCrawler

    def parse_novel_id(self, url_or_id: str) -> int:
        return NovelService.parse_novel_id(self, url_or_id)

    def _validate_novel_id(self, novel_id: int) -> None:
        NovelService._validate_novel_id(self, novel_id)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            text = str(value).strip()
            if not text or text in {"?", "-"}:
                return None
            return int(text)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _progress_message(cls, state: dict[str, Any]) -> str:
        phase = str(state.get("phase", "START"))
        done = cls._optional_int(state.get("chapter_done")) or 0
        total = cls._optional_int(state.get("chapter_total"))
        in_flight = cls._optional_int(state.get("chapter_in_flight")) or 0
        failed = cls._optional_int(state.get("chapter_failed")) or 0
        total_text = f"{total:,}" if total is not None else "?"
        if phase == "DETAIL":
            return "작품 상세정보를 조회하고 있습니다."
        if phase == "CHAPTER_LIST":
            return "회차 목록을 조회하고 있습니다."
        if phase == "EPISODE_PARALLEL":
            return (
                "회차·댓글을 병렬 수집하고 있습니다. "
                f"완료 {done:,}/{total_text} · 처리 중 {in_flight:,}개 · 실패 {failed:,}개"
            )
        if phase == "EPISODE":
            return f"회차 데이터를 수집하고 있습니다. {done:,}/{total_text}"
        if phase == "COMMENTS":
            return f"댓글을 수집하고 있습니다. 회차 {done:,}/{total_text}"
        return "수집을 준비하고 있습니다."

    def collect_stream(
        self,
        url_or_id: str,
        *,
        poll_interval: float = 0.25,
    ) -> Iterator[CollectionProgress]:
        novel_id = self.parse_novel_id(url_or_id)
        existed = self.repository.novel_exists(novel_id)
        crawler = self.crawler_factory()
        started = time.monotonic()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: asyncio.run(crawler.process_single_work(novel_id))
            )
            while not future.done():
                state = dict(crawler.active_states.get(novel_id, {}))
                yield CollectionProgress(
                    event="PROGRESS",
                    novel_id=novel_id,
                    message=self._progress_message(state),
                    elapsed_seconds=time.monotonic() - started,
                    phase=str(state.get("phase", "START")),
                    chapter_done=self._optional_int(state.get("chapter_done")) or 0,
                    chapter_total=self._optional_int(state.get("chapter_total")),
                    chapter_in_flight=self._optional_int(state.get("chapter_in_flight")) or 0,
                    chapter_failed=self._optional_int(state.get("chapter_failed")) or 0,
                )
                time.sleep(max(0.1, poll_interval))
            raw = future.result()

        self._raise_for_failure(raw)
        changed = self.repository.save_result(novel_id, raw)
        novel = raw.get("novel") if isinstance(raw.get("novel"), dict) else {}
        result = CollectionResult(
            novel_id=novel_id,
            title=str(novel.get("title") or ""),
            change_type="UPDATE" if existed else "INSERT",
            changed_rows=changed,
        )
        yield CollectionProgress(
            event="COMPLETE",
            novel_id=novel_id,
            message="DB 저장까지 완료했습니다.",
            elapsed_seconds=time.monotonic() - started,
            phase="COMPLETE",
            result=result,
        )

    async def collect(self, url_or_id: str) -> CollectionResult:
        novel_id = self.parse_novel_id(url_or_id)
        existed = self.repository.novel_exists(novel_id)
        crawler = self.crawler_factory()
        raw = await crawler.process_single_work(novel_id)
        self._raise_for_failure(raw)
        changed = self.repository.save_result(novel_id, raw)
        novel = raw.get("novel") if isinstance(raw.get("novel"), dict) else {}
        return CollectionResult(
            novel_id=novel_id,
            title=str(novel.get("title") or ""),
            change_type="UPDATE" if existed else "INSERT",
            changed_rows=changed,
        )

    @staticmethod
    def _raise_for_failure(result: dict[str, Any]) -> None:
        if result.get("type") == "SUCCESS":
            return
        log = result.get("status_log") if isinstance(result.get("status_log"), dict) else {}
        reason = str(log.get("failure_type") or "UNKNOWN_COLLECTION_ERROR")
        status = log.get("http_status")
        if status in {403, 429} or "BLOCKED" in reason:
            raise CollectionBlockedError(f"문피아가 요청을 제한했습니다 ({reason}).")
        if status not in {None, "", 200, "200"}:
            raise CollectionHttpError(f"문피아 API 요청에 실패했습니다 ({reason}).")
        raise CollectionApiError(f"문피아 단건 수집에 실패했습니다: {reason}")
