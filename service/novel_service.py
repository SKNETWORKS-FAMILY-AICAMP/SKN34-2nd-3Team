from __future__ import annotations

import asyncio
import csv
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from clawler.munpia_crawler import (
    ALL_HEADERS,
    CsvSchemaError,
    ERDCSVManager,
    MunpiaCrawler,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "db" / "data"
AUDIT_DIR = PROJECT_ROOT / "db" / "audit"

PAGE_SIZE = 20

MASTER_TABLES = (
    "novel_author",
    "novel_group",
    "novel_genre",
    "tag",
)

NOVEL_SCOPED_TABLES = (
    "novel_tag",
    "novel",
    "novel_statistics",
    "episode",
    "comment",
)

PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "novel_author": ("author_id",),
    "novel_group": ("novel_group_id",),
    "novel_genre": ("genre_id",),
    "tag": ("tag_id",),
    "novel_tag": ("novel_id", "tag_id"),
    "novel": ("novel_id",),
    "novel_statistics": ("novel_id",),
    "episode": ("episode_id",),
    "comment": ("comment_id",),
}


class NovelServiceError(RuntimeError):
    pass


class InvalidNovelInputError(NovelServiceError):
    """Raised when a link or novel_id cannot be parsed."""


@dataclass(frozen=True)
class CollectResult:
    novel_id: int
    change_type: str  # INSERT | UPDATE
    title: str
    changed_rows: dict[str, int]


@dataclass(frozen=True)
class NovelPage:
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    total_rows: int
    total_pages: int


@dataclass(frozen=True)
class CollectProgress:
    event: str
    novel_id: int
    phase: str = ""
    message: str = ""
    elapsed_seconds: float = 0.0
    chapter_done: int = 0
    chapter_total: int | None = None
    chapter_in_flight: int = 0
    chapter_failed: int = 0
    episode_number: str = ""
    comment_page: int | None = None
    comment_total_pages: int | None = None
    result: CollectResult | None = None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _row_key(
    row: dict[str, Any],
    columns: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(_text(row.get(column)).strip() for column in columns)


def _normalize_rows(
    value: Any,
    headers: list[str],
) -> list[dict[str, str]]:
    if value is None:
        return []
    rows = [value] if isinstance(value, dict) else value
    if not isinstance(rows, list):
        return []

    result: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append({
            column: _text(row.get(column, ""))
            for column in headers
        })
    return result


def _read_csv(
    path: Path,
    headers: list[str],
) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace",
    ) as file:
        reader = csv.DictReader(file)
        actual = reader.fieldnames or []
        if actual != headers:
            raise CsvSchemaError(
                f"{path.name} 헤더가 현재 ERD 규격과 다릅니다.\n"
                f"현재: {actual}\n"
                f"기대: {headers}"
            )
        return [
            {
                column: _text(row.get(column, ""))
                for column in headers
            }
            for row in reader
        ]


def _atomic_write_csv(
    path: Path,
    headers: list[str],
    rows: Iterable[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            delete=False,
            dir=path.parent,
            prefix=f".{path.stem}_",
            suffix=".tmp",
        ) as file:
            temp_path = Path(file.name)
            writer = csv.DictWriter(
                file,
                fieldnames=headers,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    column: _text(row.get(column, ""))
                    for column in headers
                })

        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _upsert_master(
    current: list[dict[str, str]],
    incoming: list[dict[str, str]],
    key_columns: tuple[str, ...],
) -> list[dict[str, str]]:
    """
    공통 마스터 테이블은 PK 기준으로 최신 API 값을 무조건 덮어쓴다.
    기존 순서는 유지하고, 신규 PK만 뒤에 추가한다.
    """
    result = list(current)
    index = {
        _row_key(row, key_columns): position
        for position, row in enumerate(result)
    }

    for row in incoming:
        key = _row_key(row, key_columns)
        if not all(key):
            continue

        if key in index:
            result[index[key]] = row
        else:
            index[key] = len(result)
            result.append(row)

    return result


def _replace_novel_scope(
    current: list[dict[str, str]],
    incoming: list[dict[str, str]],
    novel_id: int,
    key_columns: tuple[str, ...],
) -> list[dict[str, str]]:
    """
    작품 종속 테이블은 같은 novel_id의 기존 행을 전부 지운 뒤,
    이번 API 결과로 완전히 교체한다.
    """
    target = str(novel_id)

    result = [
        row
        for row in current
        if _text(row.get("novel_id")).strip() != target
    ]

    # API 결과 내부에 같은 PK가 중복되면 마지막 행을 사용한다.
    deduplicated: dict[tuple[str, ...], dict[str, str]] = {}
    for row in incoming:
        key = _row_key(row, key_columns)
        if not all(key):
            continue
        deduplicated[key] = row

    result.extend(deduplicated.values())
    return result


class NovelService:
    def __init__(
        self,
        data_dir: Path = DATA_DIR,
        audit_dir: Path = AUDIT_DIR,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.audit_dir = Path(audit_dir)

    @staticmethod
    def extract_novel_id(link_or_id: str) -> int:
        value = str(link_or_id or "").strip()
        if not value:
            raise InvalidNovelInputError(
                "문피아 작품 링크 또는 novel_id를 입력하세요."
            )

        if value.isdigit():
            return int(value)

        patterns = (
            r"/novel/detail/(\d+)",
            r"novel\.munpia\.com/(\d+)",
            r"/novel/(\d+)",
            r"[?&](?:novelId|novel_id|id)=(\d+)",
        )
        for pattern in patterns:
            match = re.search(pattern, value, re.IGNORECASE)
            if match:
                return int(match.group(1))

        raise InvalidNovelInputError(
            "입력값에서 novel_id를 찾지 못했습니다."
        )

    def _path(self, table: str) -> Path:
        return self.data_dir / f"{table}.csv"

    def _novel_exists(self, novel_id: int) -> bool:
        headers = ALL_HEADERS["novel"]
        rows = _read_csv(self._path("novel"), headers)
        target = str(novel_id)
        return any(
            _text(row.get("novel_id")).strip() == target
            for row in rows
        )

    def _create_crawler(self) -> MunpiaCrawler:
        # manager는 기존 ERD CSV와 ID 매핑을 읽는 용도로 사용한다.
        # collect_one_sync()는 결과를 CSV에 직접 쓰지 않는다.
        manager = ERDCSVManager(
            data_dir=self.data_dir,
            audit_dir=self.audit_dir,
            target_ids=[],
        )
        return MunpiaCrawler(
            manager=manager,
            target_ids=[],
        )

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            text = str(value).strip()
            if not text or text in {"?", "-"}:
                return None
            return int(text)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _progress_message(state: dict[str, Any]) -> str:
        phase = str(state.get("phase", "START"))
        chapter_done = NovelService._optional_int(
            state.get("chapter_done")
        ) or 0
        chapter_total = NovelService._optional_int(
            state.get("chapter_total")
        )
        chapter_in_flight = (
            NovelService._optional_int(
                state.get("chapter_in_flight")
            )
            or 0
        )
        chapter_failed = (
            NovelService._optional_int(
                state.get("chapter_failed")
            )
            or 0
        )
        episode_number = str(
            state.get("episode_number", "")
        ).strip()
        comment_page = NovelService._optional_int(
            state.get("comment_page")
        )
        comment_total_pages = NovelService._optional_int(
            state.get("comment_total_pages")
        )

        if phase == "DETAIL":
            return "작품 상세정보를 조회하고 있습니다."

        if phase == "CHAPTER_LIST":
            return "회차 목록을 조회하고 있습니다."

        if phase == "EPISODE_PARALLEL":
            total = (
                f"{chapter_total:,}"
                if chapter_total is not None
                else "?"
            )
            return (
                f"회차·댓글을 병렬 수집하고 있습니다. "
                f"완료 {chapter_done:,}/{total} · "
                f"처리 중 {chapter_in_flight:,}개 · "
                f"실패 {chapter_failed:,}개"
            )

        if phase == "EPISODE":
            total = (
                f"{chapter_total:,}"
                if chapter_total is not None
                else "?"
            )
            episode = (
                f" · 현재 회차 {episode_number}"
                if episode_number and episode_number != "-"
                else ""
            )
            return (
                f"회차 데이터를 수집하고 있습니다. "
                f"{chapter_done:,}/{total}{episode}"
            )

        if phase == "COMMENTS":
            total = (
                f"{chapter_total:,}"
                if chapter_total is not None
                else "?"
            )
            page_text = ""
            if comment_page is not None:
                page_total = (
                    str(comment_total_pages)
                    if comment_total_pages is not None
                    else "?"
                )
                page_text = (
                    f" · 댓글 페이지 "
                    f"{comment_page:,}/{page_total}"
                )
            episode = (
                f" · 현재 회차 {episode_number}"
                if episode_number and episode_number != "-"
                else ""
            )
            return (
                f"댓글을 수집하고 있습니다. "
                f"회차 {chapter_done:,}/{total}"
                f"{episode}{page_text}"
            )

        return "수집을 준비하고 있습니다."

    def collect_or_update_stream(
        self,
        link_or_id: str,
        poll_interval: float = 0.35,
    ):
        novel_id = self.extract_novel_id(link_or_id)
        existed_before = self._novel_exists(novel_id)

        crawler = self._create_crawler()
        started_at = time.monotonic()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                crawler.collect_one_sync,
                novel_id,
            )

            while not future.done():
                state = dict(
                    crawler.active_states.get(
                        novel_id,
                        {},
                    )
                )

                phase = str(state.get("phase", "START"))
                chapter_done = (
                    self._optional_int(
                        state.get("chapter_done")
                    )
                    or 0
                )
                chapter_total = self._optional_int(
                    state.get("chapter_total")
                )
                chapter_in_flight = (
                    self._optional_int(
                        state.get("chapter_in_flight")
                    )
                    or 0
                )
                chapter_failed = (
                    self._optional_int(
                        state.get("chapter_failed")
                    )
                    or 0
                )
                episode_number = str(
                    state.get("episode_number", "")
                ).strip()
                comment_page = self._optional_int(
                    state.get("comment_page")
                )
                comment_total_pages = self._optional_int(
                    state.get("comment_total_pages")
                )

                yield CollectProgress(
                    event="PROGRESS",
                    novel_id=novel_id,
                    phase=phase,
                    message=self._progress_message(state),
                    elapsed_seconds=(
                        time.monotonic() - started_at
                    ),
                    chapter_done=chapter_done,
                    chapter_total=chapter_total,
                    chapter_in_flight=chapter_in_flight,
                    chapter_failed=chapter_failed,
                    episode_number=episode_number,
                    comment_page=comment_page,
                    comment_total_pages=comment_total_pages,
                )

                time.sleep(max(0.1, poll_interval))

            result = future.result()

        if result.get("type") != "SUCCESS":
            status = result.get("status_log") or {}
            reason = (
                status.get("failure_type")
                or status.get("parse_status")
                or "UNKNOWN_ERROR"
            )
            raise NovelServiceError(str(reason))

        changed_rows = self._overwrite_from_result(
            novel_id=novel_id,
            result=result,
        )

        novel_row = result.get("novel") or {}
        title = _text(novel_row.get("title")).strip()

        collect_result = CollectResult(
            novel_id=novel_id,
            change_type=(
                "UPDATE"
                if existed_before
                else "INSERT"
            ),
            title=title,
            changed_rows=changed_rows,
        )

        yield CollectProgress(
            event="COMPLETE",
            novel_id=novel_id,
            phase="COMPLETE",
            message="CSV 반영까지 완료했습니다.",
            elapsed_seconds=(
                time.monotonic() - started_at
            ),
            result=collect_result,
        )

    def collect_or_update(
        self,
        link_or_id: str,
    ) -> CollectResult:
        novel_id = self.extract_novel_id(link_or_id)
        existed_before = self._novel_exists(novel_id)

        crawler = self._create_crawler()
        result = crawler.collect_one_sync(novel_id)

        if result.get("type") != "SUCCESS":
            status = result.get("status_log") or {}
            reason = (
                status.get("failure_type")
                or status.get("parse_status")
                or "UNKNOWN_ERROR"
            )
            raise NovelServiceError(str(reason))

        changed_rows = self._overwrite_from_result(
            novel_id=novel_id,
            result=result,
        )

        novel_row = result.get("novel") or {}
        title = _text(novel_row.get("title")).strip()

        return CollectResult(
            novel_id=novel_id,
            change_type="UPDATE" if existed_before else "INSERT",
            title=title,
            changed_rows=changed_rows,
        )

    def _overwrite_from_result(
        self,
        novel_id: int,
        result: dict[str, Any],
    ) -> dict[str, int]:
        changed: dict[str, int] = {}

        # 공통 마스터: PK 기준 무조건 최신값으로 교체
        for table in MASTER_TABLES:
            headers = ALL_HEADERS[table]
            current = _read_csv(self._path(table), headers)
            incoming = _normalize_rows(result.get(table), headers)
            merged = _upsert_master(
                current=current,
                incoming=incoming,
                key_columns=PRIMARY_KEYS[table],
            )
            _atomic_write_csv(self._path(table), headers, merged)
            changed[table] = len(incoming)

        # 작품 종속: 같은 novel_id 전부 삭제 후 최신 API 결과로 교체
        for table in NOVEL_SCOPED_TABLES:
            headers = ALL_HEADERS[table]
            current = _read_csv(self._path(table), headers)
            incoming = _normalize_rows(result.get(table), headers)
            merged = _replace_novel_scope(
                current=current,
                incoming=incoming,
                novel_id=novel_id,
                key_columns=PRIMARY_KEYS[table],
            )
            _atomic_write_csv(self._path(table), headers, merged)
            changed[table] = len(incoming)

        # novel_ai_evaluation.csv는 크롤러 수집 대상이 아니므로 건드리지 않는다.
        return changed

    def list_novels(
        self,
        page: int = 1,
        page_size: int = PAGE_SIZE,
    ) -> NovelPage:
        if page_size <= 0:
            raise NovelServiceError("page_size는 1 이상이어야 합니다.")

        novel_headers = ALL_HEADERS["novel"]
        statistic_headers = ALL_HEADERS["novel_statistics"]
        author_headers = ALL_HEADERS["novel_author"]

        novels = _read_csv(
            self._path("novel"),
            novel_headers,
        )
        statistics = _read_csv(
            self._path("novel_statistics"),
            statistic_headers,
        )
        authors = _read_csv(
            self._path("novel_author"),
            author_headers,
        )

        statistics_by_novel = {
            _text(row.get("novel_id")).strip(): row
            for row in statistics
            if _text(row.get("novel_id")).strip()
        }
        author_name_by_id = {
            _text(row.get("author_id")).strip(): _text(
                row.get("author_name")
            )
            for row in authors
            if _text(row.get("author_id")).strip()
        }

        display_rows: list[dict[str, Any]] = []

        # 정렬하지 않고 novel.csv의 현재 순서를 그대로 사용한다.
        for novel in novels:
            novel_id = _text(novel.get("novel_id")).strip()
            author_id = _text(novel.get("author_id")).strip()
            stats = statistics_by_novel.get(novel_id, {})

            display_rows.append({
                # ERD 기준 컬럼명
                "novel_id": novel_id,
                "title": novel.get("title", ""),
                "author_id": author_id,
                # novel.csv의 원본 보존 컬럼 우선, 없으면 author 테이블 조인
                "author_name": (
                    novel.get("author_name")
                    or author_name_by_id.get(author_id, "")
                ),
                "group_id": novel.get("group_id", ""),
                "genre_1": novel.get("genre_1", ""),
                "genre_2": novel.get("genre_2", ""),
                "free": novel.get("free", ""),
                "paid_serial": novel.get("paid_serial", ""),
                "pause": novel.get("pause", ""),
                "finish": novel.get("finish", ""),
                "view_count": stats.get("view_count", ""),
                "preference_count": stats.get(
                    "preference_count",
                    "",
                ),
                "like_count": stats.get("like_count", ""),
                "chapter_count": stats.get("chapter_count", ""),
                "free_chapter_count": stats.get(
                    "free_chapter_count",
                    "",
                ),
                "collected_at": novel.get("collected_at", ""),
                "crawl_status": novel.get("crawl_status", ""),
            })

        total_rows = len(display_rows)
        total_pages = max(
            1,
            (total_rows + page_size - 1) // page_size,
        )
        page = max(1, min(int(page), total_pages))

        start = (page - 1) * page_size
        end = start + page_size

        return NovelPage(
            rows=display_rows[start:end],
            page=page,
            page_size=page_size,
            total_rows=total_rows,
            total_pages=total_pages,
        )

    def find_page_of_novel(
        self,
        novel_id: int,
        page_size: int = PAGE_SIZE,
    ) -> int:
        headers = ALL_HEADERS["novel"]
        rows = _read_csv(self._path("novel"), headers)
        target = str(novel_id)

        for index, row in enumerate(rows):
            if _text(row.get("novel_id")).strip() == target:
                return (index // page_size) + 1

        return 1
