from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp


# ============================================================
# 출력 구조
# ============================================================
# db/data/  : ERD에 정의된 실제 테이블 CSV만 저장
# db/audit/ : 상태 로그, 댓글 검증, PK/FK 검증, 스키마 매핑 보고서
#
# db/data/
#   tag.csv, novel_tag.csv, novel_genre.csv, novel_author.csv,
#   novel_group.csv, novel.csv, episode.csv, comment.csv,
#   novel_statistics.csv, novel_ai_evaluation.csv
#
# 입력:
#   db/data/works.csv의 기존 work_id 목록만 사용
#
# db/audit/
#   status_log.csv, comment_audit.csv, schema_mapping_report.csv,
#   duplicate_keys.csv, orphan_foreign_keys.csv,
#   comment_count_mismatches.csv, validation_summary.json
#
# ============================================================
# 1. 실행 설정
# ============================================================
# 기존에 수집된 작품 목록. work_id 또는 novel_id 컬럼을 자동 인식합니다.
SOURCE_ID_CSV_CANDIDATES = (
    Path("db/data/works.csv"),
    Path("db/data/novel.csv"),
)


def resolve_source_id_csv() -> Path:
    for candidate in SOURCE_ID_CSV_CANDIDATES:
        if candidate.is_file():
            return candidate
    return SOURCE_ID_CSV_CANDIDATES[0]


SOURCE_ID_CSV = resolve_source_id_csv()

# 테스트 시 정수로 설정하면 앞 N개 작품만 처리합니다. 전체는 None.
MAX_TARGETS: int | None = None

CONCURRENCY_LIMIT = 80
SINGLE_NOVEL_EPISODE_CONCURRENCY = 20
DELAY_BETWEEN_REQS = 0.01
REQUEST_TIMEOUT_SECONDS = 30

# 진행상태 출력 주기(초)
PROGRESS_INTERVAL_SECONDS = 5

# 작품 하나가 이 시간을 넘기면 실패 처리하고 순차 저장을 계속합니다.
WORK_TIMEOUT_SECONDS = 900

# 댓글 페이지가 이 값 이상이면 전체 수집 대신 가장 오래된 댓글만 샘플링합니다.
EXCESSIVE_COMMENT_PAGE_THRESHOLD = 1000
EXCESSIVE_COMMENT_SAMPLE_LIMIT = 100

DATA_DIR = Path("db/data")
AUDIT_DIR = Path("db/audit")
VALIDATION_DIR = AUDIT_DIR

BLOCKING_HTTP_STATUSES = {403, 429}
SUCCESS_CODE = "M000_00000"
RUN_VALIDATION_ON_FINISH = False

# 테스트할 때만 예:
# MAX_TARGETS = 100
#
# 이 버전은 1~550000 전체 번호를 조회하지 않습니다.
# SOURCE_ID_CSV에 실제로 존재하는 작품 ID만 다시 조회합니다.


# ============================================================
# 2. 로그인 쿠키
# 저장 위치: 프로젝트 루트 .env
#
# .env 예:
# MUNPIA_COOKIE=key1=value1; key2=value2
#
# 쿠키가 없거나 만료된 상태에서 로그인 권한이 필요한 댓글 API를
# 호출하면 A002_14003 / "권한이 없습니다."가 반환될 수 있습니다.
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def _load_dotenv_fallback(path: Path) -> None:
    """python-dotenv가 없어도 단순 KEY=VALUE 형식은 읽습니다."""
    if not path.is_file():
        return

    for raw_line in path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]

        if key and key not in os.environ:
            os.environ[key] = value


def load_project_env() -> None:
    """프로젝트 루트와 현재 작업 폴더의 .env를 읽습니다."""
    loaded = False

    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ENV_PATH, override=False)
        cwd_env = Path.cwd() / ".env"
        if cwd_env.resolve() != ENV_PATH.resolve():
            load_dotenv(cwd_env, override=False)
        loaded = True
    except ImportError:
        pass

    if not loaded:
        _load_dotenv_fallback(ENV_PATH)
        cwd_env = Path.cwd() / ".env"
        if cwd_env.resolve() != ENV_PATH.resolve():
            _load_dotenv_fallback(cwd_env)


def parse_cookie_string(value: str) -> dict[str, str]:
    cookies: dict[str, str] = {}

    for part in str(value or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue

        name, content = part.split("=", 1)
        name = name.strip()
        content = content.strip()

        if name:
            cookies[name] = content

    return cookies


def load_munpia_cookies() -> dict[str, str]:
    load_project_env()
    return parse_cookie_string(
        os.getenv("MUNPIA_COOKIE", "")
    )


# 하위 호환용 전역값. 실제 세션에는 MunpiaCrawler.cookies를 사용합니다.
MUNPIA_COOKIES = load_munpia_cookies()


# ============================================================
# 3. ERD 스키마 + ERD에 없는 원본 컬럼
# ERD 컬럼을 먼저 배치하고, 원본 보존 컬럼을 뒤에 둔다.
# ============================================================
ERD_HEADERS: dict[str, list[str]] = {
    "tag": [
        "tag_id", "tag_name",
    ],
    "novel_tag": [
        "novel_id", "tag_id",
    ],
    "novel_genre": [
        "genre_id", "genre_name",
    ],
    "novel_author": [
        "author_id", "author_name", "author_url", "is_illustrator",
    ],
    "novel_group": [
        "novel_group_id", "group_name",
    ],
    "novel": [
        "novel_id", "source_url", "title", "introduction",
        "author_id", "illustrator_id", "origin_cover_url", "group_id",
        "free", "paid_serial", "exclusive", "pre_exclusive", "adult",
        "contest", "rental", "pause", "finish", "epub", "ebook",
        "cp_novel", "created_at", "updated_at",
        "paid_conversion_open_at", "isbn", "period", "unit_type",
        "collected_at", "genre_1", "genre_2",
    ],
    "episode": [
        "episode_id", "novel_id", "episode_number", "episode_title",
        "published_at", "access_type", "view_count", "like_count",
        "comment_count", "page_count", "adult",
        "paid_conversion_before_entry", "up", "collected_at",
    ],
    "comment": [
        "comment_id", "novel_id", "episode_id", "parent_comment_id",
        "reply_level", "content_type", "comment_text", "like_count",
        "dislike_count", "created_at", "secret", "report_status",
        "block_status", "collected_at",
    ],
    "novel_statistics": [
        "novel_id", "view_count", "preference_count", "like_count",
        "chapter_count", "free_chapter_count", "characters",
        "male_count", "female_count", "age_10s_percent",
        "age_20s_percent", "age_30s_percent", "age_40s_percent",
        "age_50s_percent", "source_notice_count", "collected_at",
    ],
    "novel_ai_evaluation": [
        "evaluation_id", "novel_id", "evaluation_type",
        "evaluation_level", "evaluation_score", "confidence",
        "model_version", "analyzed_at",
    ],
}

# ERD에 없지만 원본 정보 보존을 위해 유지
EXTRA_HEADERS: dict[str, list[str]] = {
    "tag": ["first_seen_novel_id", "collected_at"],
    "novel_tag": ["collected_at"],
    "novel_genre": [
        "genre_best_code", "genre_best_name",
        "first_seen_novel_id", "collected_at",
    ],
    "novel_author": [],
    "novel_group": ["first_seen_novel_id", "collected_at"],
    "novel": [
        "author_name", "illustrator_name", "cover_url", "group_name",
        "genres_json", "tags_json", "genre_best_name", "genre_best_code",
        "notices_json", "events_json", "crawl_status",
        "source_http_status",
    ],
    "episode": ["source_url", "crawl_status", "comment_crawl_status"],
    "comment": ["crawl_status"],
    "novel_statistics": [],
    "novel_ai_evaluation": [],
}

ALL_HEADERS = {
    key: ERD_HEADERS[key] + EXTRA_HEADERS.get(key, [])
    for key in ERD_HEADERS
}

STATUS_LOG_HEADERS = [
    "candidate_novel_id", "source_url", "http_status", "parse_status",
    "failure_type", "attempt_count", "last_attempt_at", "accepted",
]

COMMENT_AUDIT_HEADERS = [
    "novel_id", "episode_id", "episode_number",
    "declared_comment_count", "actual_comment_count",
    "difference", "audit_status", "http_status",
    "api_code", "api_message", "checked_at",
]



class CsvSchemaError(RuntimeError):
    pass


def nullable(value: Any) -> Any:
    return "" if value is None else value


def to_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value or "").strip().replace(",", "")
        return int(float(text)) if text else default
    except (TypeError, ValueError):
        return default


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def load_existing_novel_ids(path: Path) -> list[int]:
    """
    기존 CSV에서 실제 수집된 작품 ID만 읽습니다.

    지원 컬럼:
    - work_id: 기존 works.csv
    - novel_id: ERD 변환 후 novel.csv

    중복·빈 값·음수 ID는 제거하고 오름차순으로 반환합니다.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"기존 작품 ID CSV를 찾을 수 없습니다: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace",
    ) as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []

        if "work_id" in fieldnames:
            id_column = "work_id"
        elif "novel_id" in fieldnames:
            id_column = "novel_id"
        else:
            raise CsvSchemaError(
                f"{path}에 work_id 또는 novel_id 컬럼이 없습니다. "
                f"현재 컬럼={fieldnames}"
            )

        ids: set[int] = set()
        invalid_rows = 0

        for row in reader:
            novel_id = to_int(row.get(id_column), -1)
            if novel_id < 0:
                invalid_rows += 1
                continue
            ids.add(novel_id)

    ordered = sorted(ids)

    print(
        f"📚 기존 작품 ID 로드 | 파일 {path} | "
        f"고유 ID {len(ordered):,}개 | 무효 행 {invalid_rows:,}개"
    )
    return ordered


class ERDCSVManager:
    """ERD 테이블당 CSV 하나를 관리하고 작품 ID 순서대로 기록한다."""

    def __init__(
        self,
        data_dir: Path,
        audit_dir: Path,
        target_ids: list[int],
    ) -> None:
        self.data_dir = data_dir
        self.audit_dir = audit_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()

        self.files = {
            key: self.data_dir / f"{key}.csv"
            for key in ALL_HEADERS
        }
        self.files["status_log"] = self.audit_dir / "status_log.csv"
        self.files["comment_audit"] = self.audit_dir / "comment_audit.csv"

        for key, path in self.files.items():
            headers = (
                STATUS_LOG_HEADERS if key == "status_log"
                else COMMENT_AUDIT_HEADERS if key == "comment_audit"
                else ALL_HEADERS[key]
            )
            self._ensure_file(path, headers)
            self._validate_header(path, headers)

        self.processed_novels = self._load_int_keys(
            self.files["status_log"],
            "candidate_novel_id",
        )
        self.seen_tags = self._load_int_keys(self.files["tag"], "tag_id")
        self.seen_genres_by_name = self._load_text_map(
            self.files["novel_genre"], "genre_name", "genre_id"
        )
        self.seen_groups_by_name = self._load_text_map(
            self.files["novel_group"], "group_name", "novel_group_id"
        )
        self.author_id_by_url: dict[str, int] = {}
        self.author_id_by_name: dict[str, int] = {}
        self.author_rows_by_id: dict[int, dict[str, Any]] = {}
        self._load_authors()

        self.next_author_id = max(self.author_rows_by_id, default=0) + 1
        self.next_genre_id = max(
            (to_int(v) for v in self.seen_genres_by_name.values()),
            default=0,
        ) + 1
        self.next_group_id = max(
            (to_int(v) for v in self.seen_groups_by_name.values()),
            default=0,
        ) + 1

        self.buffer: dict[int, dict[str, Any]] = {}

        # 실제 대상 ID 순서만 관리합니다.
        # 번호 사이의 빈 구간을 기다리지 않으므로 sparse ID에서도 멈추지 않습니다.
        self.target_order = [
            novel_id
            for novel_id in sorted(set(target_ids))
            if novel_id not in self.processed_novels
        ]
        self.target_index = 0

        self._write_schema_mapping_report()

    @staticmethod
    def _ensure_file(path: Path, headers: list[str]) -> None:
        if path.exists():
            return
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(headers)

    @staticmethod
    def _validate_header(path: Path, headers: list[str]) -> None:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            actual = next(csv.reader(f), None)
        if actual != headers:
            raise CsvSchemaError(
                f"{path} 헤더 불일치\n현재={actual}\n기대={headers}"
            )

    @staticmethod
    def _load_int_keys(path: Path, column: str) -> set[int]:
        values: set[int] = set()
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                value = to_int(row.get(column), -1)
                if value >= 0:
                    values.add(value)
        return values

    @staticmethod
    def _load_text_map(path: Path, key_col: str, value_col: str) -> dict[str, str]:
        values: dict[str, str] = {}
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = str(row.get(key_col) or "").strip()
                value = str(row.get(value_col) or "").strip()
                if key and value:
                    values[key] = value
        return values

    @staticmethod
    def normalize_author_url(value: Any) -> str:
        raw = str(value or "").strip().rstrip("/")
        if not raw:
            return ""
        if raw.startswith(("http://", "https://")):
            return raw
        return f"https://library.munpia.com/{raw.lstrip('/')}"

    def _load_authors(self) -> None:
        with self.files["novel_author"].open(
            "r", encoding="utf-8-sig", newline=""
        ) as f:
            for row in csv.DictReader(f):
                author_id = to_int(row.get("author_id"), -1)
                if author_id < 0:
                    continue
                url = self.normalize_author_url(row.get("author_url"))
                self.author_rows_by_id[author_id] = row

                name_key = self.normalize_author_name(
                    row.get("author_name")
                )
                if name_key:
                    self.author_id_by_name.setdefault(
                        name_key,
                        author_id,
                    )

                if url:
                    self.author_id_by_url[url] = author_id

    @staticmethod
    def normalize_author_name(value: Any) -> str:
        return re.sub(
            r"\s+",
            " ",
            str(value or "").strip(),
        ).casefold()

    def resolve_author(
        self,
        author_name: str,
        author_url: str,
        is_illustrator: bool,
    ) -> tuple[int | None, dict[str, Any] | None]:
        name = str(author_name or "").strip()
        name_key = self.normalize_author_name(name)
        url = self.normalize_author_url(author_url)

        if url:
            existing = self.author_id_by_url.get(url)
            if existing is not None:
                return existing, None

        # URL이 없는 작가도 이름으로 기존 행을 찾거나 새 행을 만들어
        # novel.author_id가 고아가 되는 것을 막습니다.
        if name_key:
            existing = self.author_id_by_name.get(name_key)
            if existing is not None:
                if url:
                    self.author_id_by_url.setdefault(url, existing)
                return existing, None

        if not name and not url:
            return None, None

        author_id = self.next_author_id
        self.next_author_id += 1

        row = {
            "author_id": author_id,
            "author_name": name,
            "author_url": url,
            "is_illustrator": bool(is_illustrator),
        }

        if url:
            self.author_id_by_url[url] = author_id
        if name_key:
            self.author_id_by_name[name_key] = author_id

        self.author_rows_by_id[author_id] = row
        return author_id, row

    def resolve_genres(
        self,
        genres: list[str],
        *,
        novel_id: int,
        genre_best_code: str,
        genre_best_name: str,
        collected_at: str,
    ) -> tuple[list[int], list[dict[str, Any]]]:
        ids: list[int] = []
        new_rows: list[dict[str, Any]] = []
        for name in [str(x).strip() for x in genres if str(x).strip()]:
            genre_id_text = self.seen_genres_by_name.get(name)
            if genre_id_text:
                ids.append(to_int(genre_id_text))
                continue
            genre_id = self.next_genre_id
            self.next_genre_id += 1
            self.seen_genres_by_name[name] = str(genre_id)
            ids.append(genre_id)
            new_rows.append({
                "genre_id": genre_id,
                "genre_name": name,
                "genre_best_code": genre_best_code,
                "genre_best_name": genre_best_name,
                "first_seen_novel_id": novel_id,
                "collected_at": collected_at,
            })
        return ids, new_rows

    def resolve_group(
        self,
        group_name: str,
        *,
        novel_id: int,
        collected_at: str,
    ) -> tuple[int | None, dict[str, Any] | None]:
        name = str(group_name or "").strip()
        if not name:
            return None, None
        existing = self.seen_groups_by_name.get(name)
        if existing:
            return to_int(existing), None
        group_id = self.next_group_id
        self.next_group_id += 1
        self.seen_groups_by_name[name] = str(group_id)
        return group_id, {
            "novel_group_id": group_id,
            "group_name": name,
            "first_seen_novel_id": novel_id,
            "collected_at": collected_at,
        }

    def _next_expected_id(self) -> int | None:
        while self.target_index < len(self.target_order):
            novel_id = self.target_order[self.target_index]
            if novel_id in self.processed_novels:
                self.target_index += 1
                continue
            return novel_id
        return None

    @staticmethod
    def _filter(row: dict[str, Any], headers: list[str]) -> dict[str, Any]:
        return {key: row.get(key, "") for key in headers}

    def _append(self, key: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        headers = (
            STATUS_LOG_HEADERS if key == "status_log"
            else COMMENT_AUDIT_HEADERS if key == "comment_audit"
            else ALL_HEADERS[key]
        )
        with self.files[key].open("a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writerows(self._filter(row, headers) for row in rows)

    async def push_result(self, novel_id: int, data: dict[str, Any]) -> None:
        async with self.lock:
            self.buffer[novel_id] = data

            while True:
                expected_id = self._next_expected_id()
                if expected_id is None or expected_id not in self.buffer:
                    break

                current = self.buffer.pop(expected_id)
                self._write_result(current)

                # 일반 성공 작품은 출력하지 않습니다.
                # 실패는 worker에서 즉시 출력되므로 여기서 중복 출력하지 않습니다.

                self.processed_novels.add(expected_id)
                self.target_index += 1

    def _write_result(self, data: dict[str, Any]) -> None:
        if data["type"] == "SUCCESS":
            order = [
                "novel_author", "novel_group", "novel_genre", "tag",
                "novel_tag", "novel", "novel_statistics", "episode",
                "comment", "comment_audit",
            ]
            for key in order:
                rows = data.get(key, [])
                if isinstance(rows, dict):
                    rows = [rows]
                self._append(key, rows)
        self._append("status_log", [data["status_log"]])

    def _write_schema_mapping_report(self) -> None:
        path = self.audit_dir / "schema_mapping_report.csv"
        headers = [
            "table_name", "column_name", "column_status", "note"
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for table, erd_cols in ERD_HEADERS.items():
                for col in erd_cols:
                    writer.writerow({
                        "table_name": table,
                        "column_name": col,
                        "column_status": "ERD",
                        "note": "첨부 ERD 컬럼",
                    })
                for col in EXTRA_HEADERS.get(table, []):
                    writer.writerow({
                        "table_name": table,
                        "column_name": col,
                        "column_status": "EXTRA_ORIGINAL",
                        "note": "ERD에는 없으나 원본 보존을 위해 유지",
                    })


class MunpiaCrawler:
    def __init__(
        self,
        manager: ERDCSVManager,
        target_ids: list[int],
        *,
        cookies: dict[str, str] | str | None = None,
    ) -> None:
        self.manager = manager
        self.target_ids = target_ids

        if isinstance(cookies, str):
            self.cookies = parse_cookie_string(cookies)
        elif cookies is None:
            self.cookies = load_munpia_cookies()
        else:
            self.cookies = dict(cookies)

        self.stop_event = asyncio.Event()

        self.started_at = time.monotonic()
        self.total_targets = 0
        self.completed_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.active_ids: set[int] = set()
        self.active_states: dict[int, dict[str, Any]] = {}

        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.munpia.com",
        }

    def _cookie_jar(self) -> aiohttp.CookieJar:
        jar = aiohttp.CookieJar(unsafe=True)
        if self.cookies:
            jar.update_cookies(self.cookies)
        return jar

    def _client_timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(
            total=REQUEST_TIMEOUT_SECONDS,
        )

    def _connector(
        self,
        *,
        limit: int | None = None,
    ) -> aiohttp.TCPConnector:
        resolved_limit = (
            limit
            if limit is not None
            else max(CONCURRENCY_LIMIT * 2, 100)
        )
        return aiohttp.TCPConnector(
            limit=resolved_limit,
            ttl_dns_cache=300,
        )

    async def collect_one(
        self,
        novel_id: int,
    ) -> dict[str, Any]:
        """
        기존 전체 크롤러의 작품 처리 로직으로 작품 하나만 수집합니다.

        반환값은 ERD별 dict/list 묶음이며 CSV에 기록하지 않습니다.
        PR17 서비스가 이 결과를 받아 기존 CSV/DB에 직접 upsert할 수 있습니다.
        """
        novel_id = to_int(novel_id, -1)
        if novel_id < 0:
            raise ValueError("novel_id는 0 이상의 정수여야 합니다.")

        self.stop_event.clear()
        self.active_ids.add(novel_id)
        self.active_states[novel_id] = {
            "started_at": time.monotonic(),
            "phase": "START",
            "chapter_done": 0,
            "chapter_total": "?",
            "episode_number": "-",
            "comment_page": "-",
            "comment_total_pages": "-",
        }

        async with aiohttp.ClientSession(
            headers=self.default_headers,
            timeout=self._client_timeout(),
            connector=self._connector(limit=20),
            cookie_jar=self._cookie_jar(),
        ) as session:
            try:
                return await asyncio.wait_for(
                    self.process_novel(novel_id, session),
                    timeout=WORK_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                state = self.active_states.get(novel_id, {})
                return self.fail_result(
                    novel_id,
                    (
                        f"WORK_TIMEOUT_{WORK_TIMEOUT_SECONDS}S:"
                        f"phase={state.get('phase', 'UNKNOWN')}:"
                        f"chapter={state.get('chapter_done', 0)}/"
                        f"{state.get('chapter_total', '?')}:"
                        f"episode={state.get('episode_number', '-')}:"
                        f"comment_page={state.get('comment_page', '-')}/"
                        f"{state.get('comment_total_pages', '-')}"
                    ),
                )
            except Exception as exc:
                return self.fail_result(
                    novel_id,
                    f"FATAL_ERROR:{type(exc).__name__}:{exc}",
                )
            finally:
                self.active_ids.discard(novel_id)
                self.active_states.pop(novel_id, None)

    def collect_one_sync(
        self,
        novel_id: int,
    ) -> dict[str, Any]:
        """
        동기 서비스/Streamlit용 래퍼입니다.
        이미 실행 중인 이벤트 루프 안에서는 collect_one()을 await 하세요.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.collect_one(novel_id))

        raise RuntimeError(
            "실행 중인 이벤트 루프가 있습니다. "
            "await crawler.collect_one(novel_id)를 사용하세요."
        )

    async def run(self) -> None:
        queue: asyncio.Queue[int] = asyncio.Queue()

        for novel_id in self.target_ids:
            if novel_id not in self.manager.processed_novels:
                queue.put_nowait(novel_id)

        self.total_targets = queue.qsize()
        self.started_at = time.monotonic()

        print(
            f"🚀 기존 작품 ID 기반 ERD 크롤링 시작 | "
            f"전체 대상 {len(self.target_ids):,} | "
            f"미처리 {self.total_targets:,} | "
            f"동시성 {CONCURRENCY_LIMIT} | "
            f"쿠키 {'적용' if self.cookies else '없음'}",
            flush=True,
        )

        if self.total_targets == 0:
            print("✅ 처리할 미완료 작품이 없습니다.", flush=True)
            return

        async with aiohttp.ClientSession(
            headers=self.default_headers,
            timeout=self._client_timeout(),
            connector=self._connector(),
            cookie_jar=self._cookie_jar(),
        ) as session:
            workers = [
                asyncio.create_task(self.worker(queue, session))
                for _ in range(CONCURRENCY_LIMIT)
            ]
            progress_task = asyncio.create_task(
                self.progress_reporter(queue)
            )

            await queue.join()
            self.stop_event.set()

            progress_task.cancel()
            for worker in workers:
                worker.cancel()

            await asyncio.gather(*workers, return_exceptions=True)
            await asyncio.gather(progress_task, return_exceptions=True)

        elapsed = max(time.monotonic() - self.started_at, 0.001)
        rate = self.completed_count / elapsed

        print(
            f"🏁 완료 | 처리 {self.completed_count:,}/{self.total_targets:,} | "
            f"성공 {self.success_count:,} | 실패 {self.fail_count:,} | "
            f"경과 {elapsed:.1f}초 | 평균 {rate:.2f}작품/초",
            flush=True,
        )

    async def progress_reporter(
        self,
        queue: asyncio.Queue[int],
    ) -> None:
        while not self.stop_event.is_set():
            await asyncio.sleep(PROGRESS_INTERVAL_SECONDS)

            elapsed = max(time.monotonic() - self.started_at, 0.001)
            rate = self.completed_count / elapsed
            remaining = max(
                self.total_targets - self.completed_count,
                0,
            )
            eta_seconds = (
                remaining / rate
                if rate > 0
                else None
            )

            now = time.monotonic()
            active_items: list[tuple[float, int, dict[str, Any]]] = []

            for active_id, state in self.active_states.items():
                work_elapsed = now - float(
                    state.get("started_at", now)
                )
                active_items.append(
                    (work_elapsed, active_id, state)
                )

            active_items.sort(reverse=True)

            expected_id = self.manager._next_expected_id()
            expected_state = (
                self.active_states.get(expected_id)
                if expected_id is not None
                else None
            )

            eta_text = (
                f"{eta_seconds / 60:.1f}분"
                if eta_seconds is not None
                else "계산중"
            )

            print(
                f"⏳ {self.completed_count:,}/{self.total_targets:,} "
                f"({self.completed_count / self.total_targets * 100:.1f}%) | "
                f"성공 {self.success_count:,} 실패 {self.fail_count:,} | "
                f"저장대기 {len(self.manager.buffer):,} | "
                f"다음 {expected_id if expected_id is not None else '-'} | "
                f"{rate:.1f}작품/초 | ETA {eta_text}",
                flush=True,
            )

            shown_ids: set[int] = set()

            # 순차 저장을 실제로 막고 있는 작품만 표시합니다.
            if expected_id is not None and expected_state is not None:
                expected_elapsed = now - float(
                    expected_state.get("started_at", now)
                )
                if expected_elapsed >= 10:
                    print(
                        f"   병목 {expected_id} | "
                        f"{expected_elapsed:.0f}초 | "
                        f"{expected_state.get('phase', 'START')} | "
                        f"회차 {expected_state.get('chapter_done', 0)}/"
                        f"{expected_state.get('chapter_total', '?')} | "
                        f"댓글 "
                        f"{expected_state.get('comment_page', '-')}/"
                        f"{expected_state.get('comment_total_pages', '-')}",
                        flush=True,
                    )
                    shown_ids.add(expected_id)

            # 병목과 별개로 60초 이상 걸린 최장 작업 하나만 표시합니다.
            if active_items:
                longest_elapsed, longest_id, longest_state = active_items[0]
                if (
                    longest_elapsed >= 60
                    and longest_id not in shown_ids
                ):
                    print(
                        f"   장기 {longest_id} | "
                        f"{longest_elapsed:.0f}초 | "
                        f"{longest_state.get('phase', 'START')} | "
                        f"회차 {longest_state.get('chapter_done', 0)}/"
                        f"{longest_state.get('chapter_total', '?')} | "
                        f"댓글 "
                        f"{longest_state.get('comment_page', '-')}/"
                        f"{longest_state.get('comment_total_pages', '-')}",
                        flush=True,
                    )

    async def worker(
        self,
        queue: asyncio.Queue[int],
        session: aiohttp.ClientSession,
    ) -> None:
        while not self.stop_event.is_set():
            try:
                novel_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            self.active_ids.add(novel_id)
            self.active_states[novel_id] = {
                "started_at": time.monotonic(),
                "phase": "START",
                "chapter_done": 0,
                "chapter_total": "?",
                "episode_number": "-",
                "comment_page": "-",
                "comment_total_pages": "-",
            }

            try:
                try:
                    result = await asyncio.wait_for(
                        self.process_novel(novel_id, session),
                        timeout=WORK_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    state = self.active_states.get(novel_id, {})
                    result = self.fail_result(
                        novel_id,
                        (
                            f"WORK_TIMEOUT_{WORK_TIMEOUT_SECONDS}S:"
                            f"phase={state.get('phase', 'UNKNOWN')}:"
                            f"chapter={state.get('chapter_done', 0)}/"
                            f"{state.get('chapter_total', '?')}:"
                            f"episode={state.get('episode_number', '-')}:"
                            f"comment_page={state.get('comment_page', '-')}/"
                            f"{state.get('comment_total_pages', '-')}"
                        ),
                    )
                except Exception as exc:
                    result = self.fail_result(
                        novel_id,
                        f"FATAL_ERROR:{type(exc).__name__}:{exc}",
                    )

                if result.get("type") != "SUCCESS":
                    failure = result.get("status_log", {})
                    print(
                        f"⚠️ 즉시 실패 | 작품 {novel_id} | "
                        f"{failure.get('failure_type', 'UNKNOWN')} | "
                        f"HTTP {failure.get('http_status', '')}",
                        flush=True,
                    )

                await self.manager.push_result(novel_id, result)

                self.completed_count += 1
                if result.get("type") == "SUCCESS":
                    self.success_count += 1
                else:
                    self.fail_count += 1
            finally:
                self.active_ids.discard(novel_id)
                self.active_states.pop(novel_id, None)
                queue.task_done()

            await asyncio.sleep(DELAY_BETWEEN_REQS)

    @staticmethod
    def status_log(
        novel_id: int,
        *,
        http_status: int | str = "",
        parse_status: str = "FAIL",
        failure_type: str = "",
        accepted: str = "N",
    ) -> dict[str, Any]:
        return {
            "candidate_novel_id": novel_id,
            "source_url": f"https://www.munpia.com/novel/detail/{novel_id}",
            "http_status": http_status,
            "parse_status": parse_status,
            "failure_type": failure_type,
            "attempt_count": 1,
            "last_attempt_at": now_iso(),
            "accepted": accepted,
        }

    def fail_result(
        self,
        novel_id: int,
        failure_type: str,
        http_status: int | str = "",
    ) -> dict[str, Any]:
        return {
            "type": "FAIL",
            "status_log": self.status_log(
                novel_id,
                http_status=http_status,
                failure_type=failure_type,
            ),
        }

    async def get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        referer: str,
    ) -> tuple[int, dict[str, Any], str]:
        try:
            async with session.get(url, headers={"Referer": referer}) as response:
                text = await response.text()
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {}
                return response.status, payload, text[:500]
        except Exception as exc:
            return 0, {}, f"{type(exc).__name__}:{exc}"

    async def fetch_author_info(
        self,
        session: aiohttp.ClientSession,
        blog_url: str,
    ) -> dict[str, Any] | None:
        if not blog_url:
            return None
        url = self.manager.normalize_author_url(blog_url)
        slug = url.rstrip("/").split("/")[-1]
        api_url = "https://library.munpia.com/api/library/info"
        try:
            async with session.get(
                api_url,
                headers={
                    "blogUrl": slug,
                    "Referer": url,
                    "Accept": "application/json, text/plain, */*",
                },
            ) as response:
                if response.status != 200:
                    return None
                payload = await response.json(content_type=None)
            profile = payload.get("blogProfile") or {}
            member = payload.get("memberInfo") or {}
            if not profile and not member:
                return None
            return {
                "author_name": (
                    profile.get("authorName")
                    or member.get("nickname")
                    or ""
                ),
                "author_url": self.manager.normalize_author_url(
                    profile.get("blogUrl") or slug
                ),
            }
        except Exception:
            return None

    async def process_novel(
        self,
        novel_id: int,
        session: aiohttp.ClientSession,
    ) -> dict[str, Any]:
        collected_at = now_iso()
        state = self.active_states.setdefault(novel_id, {})
        state.update(phase="DETAIL")
        source_url = f"https://www.munpia.com/novel/detail/{novel_id}"
        detail_url = (
            f"https://www.munpia.com/api/v1/pc/novel-detail/{novel_id}"
        )

        status, payload, raw = await self.get_json(
            session, detail_url, referer=source_url
        )
        if status in BLOCKING_HTTP_STATUSES:
            self.stop_event.set()
            return self.fail_result(
                novel_id, f"HTTP_{status}_BLOCKED", status
            )
        if status != 200:
            return self.fail_result(novel_id, f"HTTP_{status}:{raw}", status)
        if payload.get("code") != SUCCESS_CODE or not payload.get("result"):
            return self.fail_result(
                novel_id,
                f"API_{payload.get('code')}:{payload.get('message')}",
                status,
            )

        result = payload["result"]
        novel_info = result.get("novelInfo") or {}
        blog_url = result.get("blogUrl") or ""

        author_info = await self.fetch_author_info(session, blog_url)
        detail_author_name = str(novel_info.get("authorName") or "").strip()
        author_name = (
            str((author_info or {}).get("author_name") or "").strip()
            or detail_author_name
        )
        author_url = (
            str((author_info or {}).get("author_url") or "").strip()
            or blog_url
        )
        author_id, new_author = self.manager.resolve_author(
            author_name, author_url, False
        )

        statistics: dict[str, Any] = {}
        stat_url = (
            f"https://www.munpia.com/api/v1/pc/"
            f"novel-detail/{novel_id}/read-statistics"
        )
        stat_status, stat_payload, _ = await self.get_json(
            session, stat_url, referer=source_url
        )
        if (
            stat_status == 200
            and stat_payload.get("code") == SUCCESS_CODE
            and stat_payload.get("result")
        ):
            statistics = stat_payload["result"]

        genres = novel_info.get("genres") or []
        tags = novel_info.get("tags") or []
        genre_best_code = str(novel_info.get("genreBestCode") or "")
        genre_best_name = str(novel_info.get("genreBestName") or "")

        genre_ids, new_genres = self.manager.resolve_genres(
            genres,
            novel_id=novel_id,
            genre_best_code=genre_best_code,
            genre_best_name=genre_best_name,
            collected_at=collected_at,
        )
        group_name = str(novel_info.get("groupName") or "")
        group_id, new_group = self.manager.resolve_group(
            group_name,
            novel_id=novel_id,
            collected_at=collected_at,
        )

        new_tags: list[dict[str, Any]] = []
        novel_tags: list[dict[str, Any]] = []
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            tag_id = to_int(tag.get("id"), -1)
            if tag_id < 0:
                continue
            if tag_id not in self.manager.seen_tags:
                self.manager.seen_tags.add(tag_id)
                new_tags.append({
                    "tag_id": tag_id,
                    "tag_name": tag.get("title", ""),
                    "first_seen_novel_id": novel_id,
                    "collected_at": collected_at,
                })
            novel_tags.append({
                "novel_id": novel_id,
                "tag_id": tag_id,
                "collected_at": collected_at,
            })

        novel_row = {
            "novel_id": novel_id,
            "source_url": source_url,
            "title": novel_info.get("title", ""),
            "introduction": novel_info.get("introduction", ""),
            "author_id": author_id if author_id is not None else "",
            "illustrator_id": "",
            "origin_cover_url": novel_info.get("originCoverUrl", ""),
            "group_id": group_id if group_id is not None else "",
            "free": novel_info.get("free", ""),
            "paid_serial": novel_info.get("paidSerial", ""),
            "exclusive": novel_info.get("exclusive", ""),
            "pre_exclusive": novel_info.get("preExclusive", ""),
            "adult": novel_info.get("adult", ""),
            "contest": novel_info.get("contest", ""),
            "rental": novel_info.get("rental", ""),
            "pause": novel_info.get("pause", ""),
            "finish": novel_info.get("finish", ""),
            "epub": novel_info.get("epub", ""),
            "ebook": novel_info.get("ebook", ""),
            "cp_novel": novel_info.get("cpNovel", ""),
            "created_at": novel_info.get("createdAt", ""),
            "updated_at": novel_info.get("updatedAt", ""),
            "paid_conversion_open_at": novel_info.get(
                "paidConversionOpenAt", ""
            ),
            "isbn": novel_info.get("isbn", ""),
            "period": novel_info.get("period", ""),
            "unit_type": novel_info.get("unitType", ""),
            "collected_at": collected_at,
            "genre_1": genre_ids[0] if len(genre_ids) > 0 else "",
            "genre_2": genre_ids[1] if len(genre_ids) > 1 else "",
            # ERD 외 원본 보존
            "author_name": detail_author_name or author_name,
            "illustrator_name": novel_info.get("illustratorName", ""),
            "cover_url": novel_info.get("coverUrl", ""),
            "group_name": group_name,
            "genres_json": json.dumps(genres, ensure_ascii=False),
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "genre_best_name": genre_best_name,
            "genre_best_code": genre_best_code,
            "notices_json": json.dumps(
                (result.get("noticeInfo") or {}).get("list") or [],
                ensure_ascii=False,
            ),
            "events_json": json.dumps(
                result.get("events") or [], ensure_ascii=False
            ),
            "crawl_status": "SUCCESS",
            "source_http_status": status,
        }

        stat_row = {
            "novel_id": novel_id,
            "view_count": nullable(novel_info.get("viewCount")),
            "preference_count": nullable(novel_info.get("preferenceCount")),
            "like_count": nullable(novel_info.get("likeCount")),
            "chapter_count": nullable(novel_info.get("chapterCount")),
            "free_chapter_count": nullable(
                novel_info.get("freeChapterCount")
            ),
            "characters": nullable(novel_info.get("characters")),
            "male_count": nullable(statistics.get("maleCount")),
            "female_count": nullable(statistics.get("femaleCount")),
            "age_10s_percent": nullable(statistics.get("age10sPercent")),
            "age_20s_percent": nullable(statistics.get("age20sPercent")),
            "age_30s_percent": nullable(statistics.get("age30sPercent")),
            "age_40s_percent": nullable(statistics.get("age40sPercent")),
            "age_50s_percent": nullable(statistics.get("age50sPercent")),
            "source_notice_count": to_int(
                (result.get("noticeInfo") or {}).get("count"), 0
            ),
            "collected_at": collected_at,
        }

        episode_rows: list[dict[str, Any]] = []
        comment_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []

        # ------------------------------------------------------------
        # 1) 회차 목록은 먼저 전부 가져옵니다.
        # 2) 각 회차의 댓글 수집은 제한 병렬 처리합니다.
        # ------------------------------------------------------------
        chapters_all: list[dict[str, Any]] = []
        page = 1
        total_chapters: int | None = None
        state.update(
            phase="CHAPTER_LIST",
            chapter_done=0,
            chapter_in_flight=0,
            chapter_failed=0,
        )

        while not self.stop_event.is_set():
            chapter_url = (
                f"https://www.munpia.com/api/v1/pc/novel-detail/{novel_id}/"
                f"chapters?order=ENTRY_FIRST&page={page}&size=100"
            )
            ep_status, ep_payload, ep_raw = await self.get_json(
                session,
                chapter_url,
                referer=source_url,
            )

            if ep_status in BLOCKING_HTTP_STATUSES:
                self.stop_event.set()
                return self.fail_result(
                    novel_id,
                    f"CHAPTER_HTTP_{ep_status}_BLOCKED",
                    ep_status,
                )

            if (
                ep_status != 200
                or ep_payload.get("code") != SUCCESS_CODE
            ):
                return self.fail_result(
                    novel_id,
                    f"CHAPTER_ERROR:{ep_status}:"
                    f"{ep_payload.get('code')}:"
                    f"{ep_payload.get('message')}:"
                    f"{ep_raw}",
                    ep_status,
                )

            ep_result = ep_payload.get("result") or {}
            chapters = ep_result.get("list") or []

            if total_chapters is None:
                total_chapters = to_int(
                    ep_result.get("total"),
                    to_int(
                        novel_info.get("chapterCount"),
                        0,
                    ),
                )

            chapters_all.extend(
                chapter
                for chapter in chapters
                if to_int(chapter.get("id"), -1) >= 0
            )

            state["chapter_total"] = (
                total_chapters
                if total_chapters is not None
                else len(chapters_all)
            )

            if (
                not chapters
                or len(chapters) < 100
                or (
                    total_chapters is not None
                    and len(chapters_all) >= total_chapters
                )
            ):
                break

            page += 1
            await asyncio.sleep(0.05)

        total_work = len(chapters_all)
        state.update(
            phase="EPISODE_PARALLEL",
            chapter_total=total_work,
            chapter_done=0,
            chapter_in_flight=0,
            chapter_failed=0,
            episode_number="",
            comment_page="-",
            comment_total_pages="-",
        )

        semaphore = asyncio.Semaphore(
            SINGLE_NOVEL_EPISODE_CONCURRENCY
        )
        progress_lock = asyncio.Lock()
        completed_count = 0
        failed_count = 0

        async def process_episode(
            chapter: dict[str, Any],
        ) -> tuple[
            dict[str, Any],
            list[dict[str, Any]],
            dict[str, Any] | None,
        ]:
            nonlocal completed_count, failed_count

            episode_id = to_int(chapter.get("id"), -1)
            access_type = (
                "FREE"
                if chapter.get("free")
                else "PAID"
            )
            declared = max(
                to_int(chapter.get("commentCount"), 0),
                0,
            )

            async with semaphore:
                async with progress_lock:
                    state["chapter_in_flight"] = (
                        to_int(
                            state.get("chapter_in_flight"),
                            0,
                        )
                        + 1
                    )
                    state["episode_number"] = (
                        chapter.get("num", "")
                    )

                fetched_comments: list[dict[str, Any]] = []
                actual = 0
                comment_status = "NOT_REQUESTED_PAID"
                c_http: int | str = ""
                c_code = ""
                c_message = ""
                comment_total_pages = 0
                sample_direction = ""
                drop_reason = ""
                audit_row: dict[str, Any] | None = None

                try:
                    if access_type == "FREE":
                        (
                            fetched_comments,
                            comment_status,
                            c_http,
                            c_code,
                            c_message,
                            comment_total_pages,
                            sample_direction,
                            drop_reason,
                        ) = await self.fetch_comments(
                            session=session,
                            novel_id=novel_id,
                            episode_id=episode_id,
                            declared_count=declared,
                            collected_at=collected_at,
                            referer=source_url,
                        )

                        actual = len({
                            str(row.get("comment_id"))
                            for row in fetched_comments
                            if str(
                                row.get("comment_id") or ""
                            ).strip()
                        })

                        if (
                            comment_status == "SUCCESS"
                            and actual != declared
                        ):
                            comment_status = (
                                "SOURCE_COUNT_STALE"
                            )
                            for comment_row in fetched_comments:
                                comment_row["crawl_status"] = (
                                    "SOURCE_COUNT_STALE"
                                )

                        if comment_status == "BLOCKED":
                            self.stop_event.set()

                        if (
                            comment_status
                            == "PARTIAL_OLDEST_100"
                        ):
                            audit_status = (
                                "PARTIAL_OLDEST_100"
                            )
                        elif (
                            comment_status
                            == "SOURCE_COUNT_STALE"
                        ):
                            audit_status = (
                                "SOURCE_COUNT_STALE"
                            )
                        elif (
                            comment_status
                            == "ACCESS_UNAVAILABLE"
                        ):
                            audit_status = (
                                "ACCESS_UNAVAILABLE"
                            )
                        else:
                            audit_status = (
                                "MATCH"
                                if actual == declared
                                else "DECLARED_BUT_ZERO"
                                if declared > 0 and actual == 0
                                else "MISSING"
                                if actual < declared
                                else "OVER_COLLECTED"
                            )
                            if comment_status not in {
                                "SUCCESS",
                                "MATCH",
                            }:
                                audit_status = (
                                    f"REQUEST_{comment_status}"
                                )

                        audit_row = {
                            "novel_id": novel_id,
                            "episode_id": episode_id,
                            "episode_number": chapter.get(
                                "num",
                                "",
                            ),
                            "declared_comment_count": declared,
                            "actual_comment_count": actual,
                            "difference": actual - declared,
                            "audit_status": audit_status,
                            "http_status": c_http,
                            "api_code": c_code,
                            "api_message": (
                                f"{c_message} | "
                                f"total_pages="
                                f"{comment_total_pages} | "
                                f"sample_direction="
                                f"{sample_direction} | "
                                f"drop_reason={drop_reason}"
                                if comment_status
                                == "PARTIAL_OLDEST_100"
                                else c_message
                            ),
                            "total_pages": (
                                comment_total_pages
                            ),
                            "sample_direction": (
                                sample_direction
                            ),
                            "sampled_comment_count": actual,
                            "stored_comment_count": actual,
                            "drop_reason": drop_reason,
                            "checked_at": now_iso(),
                        }

                    episode_row = {
                        "episode_id": episode_id,
                        "novel_id": novel_id,
                        "episode_number": chapter.get(
                            "num",
                            "",
                        ),
                        "episode_title": chapter.get(
                            "title",
                            "",
                        ),
                        "published_at": chapter.get(
                            "createdAt",
                            "",
                        ),
                        "access_type": access_type,
                        "view_count": nullable(
                            chapter.get("viewCount")
                        ),
                        "like_count": nullable(
                            chapter.get("likeCount")
                        ),
                        "comment_count": declared,
                        "page_count": nullable(
                            chapter.get("pages")
                        ),
                        "adult": chapter.get("adult", ""),
                        "paid_conversion_before_entry": (
                            chapter.get(
                                "paidConversionBeforeEntry",
                                "",
                            )
                        ),
                        "up": chapter.get("up", ""),
                        "collected_at": collected_at,
                        "source_url": source_url,
                        "crawl_status": "SUCCESS",
                        "comment_crawl_status": (
                            comment_status
                        ),
                    }

                    return (
                        episode_row,
                        fetched_comments,
                        audit_row,
                    )

                except Exception:
                    async with progress_lock:
                        failed_count += 1
                        state["chapter_failed"] = (
                            failed_count
                        )
                    raise

                finally:
                    async with progress_lock:
                        completed_count += 1
                        state["chapter_done"] = (
                            completed_count
                        )
                        state["chapter_in_flight"] = max(
                            0,
                            to_int(
                                state.get(
                                    "chapter_in_flight"
                                ),
                                1,
                            )
                            - 1,
                        )

        tasks = [
            asyncio.create_task(
                process_episode(chapter)
            )
            for chapter in chapters_all
        ]

        for future in asyncio.as_completed(tasks):
            try:
                (
                    episode_row,
                    fetched_comments,
                    audit_row,
                ) = await future
            except Exception as exc:
                # 한 회차 실패가 작품 전체를 즉시 중단시키지는 않습니다.
                # 차단 상태는 stop_event로 전파됩니다.
                print(
                    f"⚠️ {novel_id} | 회차 병렬 수집 실패 | "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                continue

            episode_rows.append(episode_row)
            comment_rows.extend(fetched_comments)
            if audit_row is not None:
                audit_rows.append(audit_row)

            if self.stop_event.is_set():
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(
                    *tasks,
                    return_exceptions=True,
                )
                break

        # 정렬은 필수는 아니지만, 병렬 완료 순서가 뒤섞이는 것을 막기 위해
        # 회차 번호 기준으로만 안정적으로 정리합니다.
        episode_rows.sort(
            key=lambda row: (
                to_int(row.get("episode_number"), 0),
                to_int(row.get("episode_id"), 0),
            )
        )
        comment_rows.sort(
            key=lambda row: (
                to_int(row.get("episode_id"), 0),
                str(row.get("created_at") or ""),
                str(row.get("comment_id") or ""),
            )
        )
        audit_rows.sort(
            key=lambda row: (
                to_int(row.get("episode_number"), 0),
                to_int(row.get("episode_id"), 0),
            )
        )

        counts = Counter(row["audit_status"] for row in audit_rows)
        summary = ",".join(f"{k}:{v}" for k, v in sorted(counts.items()))

        return {
            "type": "SUCCESS",
            "novel_author": [new_author] if new_author else [],
            "novel_group": [new_group] if new_group else [],
            "novel_genre": new_genres,
            "tag": new_tags,
            "novel_tag": novel_tags,
            "novel": novel_row,
            "novel_statistics": stat_row,
            "episode": episode_rows,
            "comment": comment_rows,
            "comment_audit": audit_rows,
            "comment_validation_summary": summary,
            "status_log": self.status_log(
                novel_id,
                http_status=status,
                parse_status="SUCCESS",
                accepted="Y",
            ),
        }

    async def fetch_comments(
        self,
        *,
        session: aiohttp.ClientSession,
        novel_id: int,
        episode_id: int,
        declared_count: int,
        collected_at: str,
        referer: str,
    ) -> tuple[
        list[dict[str, Any]], str, int | str, str, str,
        int, str, str,
    ]:
        state = self.active_states.setdefault(novel_id, {})
        last_http: int | str = ""
        last_code = ""
        last_message = ""

        def convert(comment: dict[str, Any], crawl_status: str) -> dict[str, Any] | None:
            comment_id = str(comment.get("id") or "").strip()
            if not comment_id:
                return None
            parent_id = comment.get("parentId")
            return {
                "comment_id": comment_id,
                "novel_id": novel_id,
                "episode_id": episode_id,
                "parent_comment_id": "" if parent_id in (None, 0) else parent_id,
                "reply_level": comment.get("replyLevel", ""),
                "content_type": comment.get("contentType", ""),
                "comment_text": comment.get("content", ""),
                "like_count": comment.get("likeCount", ""),
                "dislike_count": comment.get("dislikeCount", ""),
                "created_at": comment.get("createdAt", ""),
                "secret": comment.get("secret", ""),
                "report_status": comment.get("report", ""),
                "block_status": comment.get("block", ""),
                "collected_at": collected_at,
                "crawl_status": crawl_status,
            }

        async def request_page(page: int) -> tuple[
            list[dict[str, Any]], int, str, str, int
        ]:
            nonlocal last_http, last_code, last_message
            state.update(
                phase="COMMENTS",
                comment_page=page,
            )
            url = (
                f"https://www.munpia.com/api/v1/pc/novel-detail/{novel_id}/"
                f"entries/{episode_id}/comments"
                f"?order=LATEST&page={page}&size=100"
            )
            status, payload, raw = await self.get_json(
                session, url, referer=referer
            )
            last_http = status
            last_code = str(payload.get("code") or "")
            last_message = str(payload.get("message") or "")

            if status in BLOCKING_HTTP_STATUSES:
                raise RuntimeError(f"BLOCKED:{status}")
            if status != 200:
                raise RuntimeError(f"HTTP_{status}:{raw}")
            if last_code != SUCCESS_CODE:
                if last_code == "A002_14003":
                    raise RuntimeError(
                        f"ACCESS_UNAVAILABLE:{last_message}"
                    )
                raise RuntimeError(
                    f"API_{last_code}:{last_message}"
                )

            result = payload.get("result") or {}
            comments = result.get("list") or []
            total_pages = max(to_int(result.get("totalPages"), 1), 1)
            state["comment_total_pages"] = total_pages
            return comments, status, last_code, last_message, total_pages

        # 첫 페이지는 totalPages 확인용입니다.
        try:
            first_comments, _, _, _, total_pages = await request_page(1)
        except RuntimeError as exc:
            message = str(exc)
            if message.startswith("BLOCKED:"):
                return [], "BLOCKED", last_http, last_code, last_message, 0, "", ""
            if message.startswith("HTTP_"):
                return [], message.split(":", 1)[0], last_http, last_code, last_message, 0, "", ""
            if message.startswith("ACCESS_UNAVAILABLE:"):
                return (
                    [], "ACCESS_UNAVAILABLE",
                    last_http, last_code, last_message,
                    0, "", "",
                )
            if message.startswith("API_"):
                return [], message.split(":", 1)[0], last_http, last_code, last_message, 0, "", ""
            return [], "UNKNOWN", last_http, last_code, last_message, 0, "", ""

        # 일반 회차: 기존 로직 그대로 최신 페이지 1 -> 마지막 페이지.
        if total_pages < EXCESSIVE_COMMENT_PAGE_THRESHOLD:
            rows_by_id: dict[str, dict[str, Any]] = {}
            page = 1
            comments = first_comments

            while not self.stop_event.is_set():
                for comment in comments:
                    row = convert(comment, "SUCCESS")
                    if row:
                        rows_by_id[str(row["comment_id"])] = row

                if not comments or page >= total_pages:
                    break

                page += 1
                try:
                    comments, _, _, _, _ = await request_page(page)
                except RuntimeError as exc:
                    message = str(exc)
                    status_name = (
                        "BLOCKED"
                        if message.startswith("BLOCKED:")
                        else "ACCESS_UNAVAILABLE"
                        if message.startswith("ACCESS_UNAVAILABLE:")
                        else message.split(":", 1)[0]
                    )
                    return (
                        list(rows_by_id.values()), status_name,
                        last_http, last_code, last_message, total_pages,
                        "LATEST_TO_OLDEST", "",
                    )
                await asyncio.sleep(0.1)

            return (
                list(rows_by_id.values()), "SUCCESS",
                last_http, last_code, last_message, total_pages,
                "LATEST_TO_OLDEST", "",
            )

        # 과도한 회차: 1페이지 데이터는 저장하지 않고 마지막 페이지로 즉시 점프합니다.
        # 마지막 -> -1 방향으로 조회해 가장 오래된 댓글 최대 100개만 남깁니다.
        page = total_pages
        page_chunks: list[tuple[int, list[dict[str, Any]]]] = []
        seen_ids: set[str] = set()

        while page >= 1 and len(seen_ids) < EXCESSIVE_COMMENT_SAMPLE_LIMIT:
            try:
                comments, _, _, _, _ = await request_page(page)
            except RuntimeError as exc:
                message = str(exc)
                status_name = (
                    "BLOCKED"
                    if message.startswith("BLOCKED:")
                    else "ACCESS_UNAVAILABLE"
                    if message.startswith("ACCESS_UNAVAILABLE:")
                    else message.split(":", 1)[0]
                )
                return (
                    [], status_name, last_http, last_code, last_message,
                    total_pages, "OLDEST_TO_NEWER",
                    "EXCESSIVE_COMMENT_PAGES",
                )

            converted: list[dict[str, Any]] = []
            for comment in comments:
                row = convert(comment, "PARTIAL_OLDEST_100")
                if not row:
                    continue
                comment_id = str(row["comment_id"])
                if comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)
                converted.append(row)

            page_chunks.append((page, converted))
            if not comments:
                break
            page -= 1
            await asyncio.sleep(0.1)

        # API의 기존 LATEST 정렬과 같은 방향으로 복원합니다.
        # page 번호가 작은 묶음이 더 최신이므로 오름차순 결합합니다.
        ordered_rows: list[dict[str, Any]] = []
        for _, chunk in sorted(page_chunks, key=lambda item: item[0]):
            ordered_rows.extend(chunk)

        # 결합 결과의 끝부분이 가장 오래된 댓글입니다. 정확히 최대 100개만 보존합니다.
        if len(ordered_rows) > EXCESSIVE_COMMENT_SAMPLE_LIMIT:
            ordered_rows = ordered_rows[-EXCESSIVE_COMMENT_SAMPLE_LIMIT:]

        print(
            f"🧹 {novel_id} | 회차 {episode_id} | "
            f"{total_pages:,}페이지 → "
            f"오래된 댓글 {len(ordered_rows):,}개 저장",
            flush=True,
        )

        return (
            ordered_rows, "PARTIAL_OLDEST_100",
            last_http, last_code, last_message, total_pages,
            "OLDEST_TO_NEWER_THEN_RESTORED_LATEST_ORDER",
            "EXCESSIVE_COMMENT_PAGES",
        )


# ============================================================
# 4. 전체 CSV 검증
# ============================================================
def validate_outputs(data_dir: Path) -> dict[str, Any]:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    db_path = VALIDATION_DIR / "validation.sqlite3"
    db_path.unlink(missing_ok=True)

    summary: dict[str, Any] = {
        "checked_at": now_iso(),
        "tables": {},
        "errors": [],
        "warnings": [],
    }

    required_files = {
        key: data_dir / f"{key}.csv"
        for key in ALL_HEADERS
    }

    # 헤더와 행 수
    for key, path in required_files.items():
        if not path.is_file():
            summary["errors"].append(f"파일 없음: {path}")
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
        if header != ALL_HEADERS[key]:
            summary["errors"].append(
                f"{key} 헤더 불일치: {header}"
            )
        summary["tables"][key] = {"rows": row_count, "header_ok": header == ALL_HEADERS[key]}

    con = sqlite3.connect(db_path)
    con.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE novel_ids(id INTEGER PRIMARY KEY);
        CREATE TABLE author_ids(id INTEGER PRIMARY KEY);
        CREATE TABLE group_ids(id INTEGER PRIMARY KEY);
        CREATE TABLE genre_ids(id INTEGER PRIMARY KEY);
        CREATE TABLE tag_ids(id INTEGER PRIMARY KEY);
        CREATE TABLE episode_ids(id INTEGER PRIMARY KEY, novel_id INTEGER);
        CREATE TABLE comment_ids(id TEXT PRIMARY KEY, novel_id INTEGER, episode_id INTEGER);
    """)

    duplicate_report = VALIDATION_DIR / "duplicate_keys.csv"
    orphan_report = VALIDATION_DIR / "orphan_foreign_keys.csv"
    comment_report = VALIDATION_DIR / "comment_count_mismatches.csv"

    dup_rows: list[dict[str, Any]] = []
    orphan_rows: list[dict[str, Any]] = []

    def load_unique(path: Path, table: str, key_col: str, sql: str, extra_cols: tuple[str, ...] = ()) -> None:
        if not path.is_file():
            return
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = str(row.get(key_col) or "").strip()
                if not key:
                    continue
                values = [key] + [to_int(row.get(c), -1) for c in extra_cols]
                try:
                    con.execute(sql, values)
                except sqlite3.IntegrityError:
                    dup_rows.append({
                        "table_name": table,
                        "key_column": key_col,
                        "duplicate_key": key,
                    })
        con.commit()

    load_unique(required_files["novel"], "novel", "novel_id", "INSERT INTO novel_ids VALUES (?)")
    load_unique(required_files["novel_author"], "novel_author", "author_id", "INSERT INTO author_ids VALUES (?)")
    load_unique(required_files["novel_group"], "novel_group", "novel_group_id", "INSERT INTO group_ids VALUES (?)")
    load_unique(required_files["novel_genre"], "novel_genre", "genre_id", "INSERT INTO genre_ids VALUES (?)")
    load_unique(required_files["tag"], "tag", "tag_id", "INSERT INTO tag_ids VALUES (?)")
    load_unique(required_files["episode"], "episode", "episode_id", "INSERT INTO episode_ids VALUES (?, ?)", ("novel_id",))
    load_unique(required_files["comment"], "comment", "comment_id", "INSERT INTO comment_ids VALUES (?, ?, ?)", ("novel_id", "episode_id"))

    # FK 검사
    fk_specs = [
        ("novel", required_files["novel"], "author_id", "author_ids", "id"),
        ("novel", required_files["novel"], "group_id", "group_ids", "id"),
        ("novel", required_files["novel"], "genre_1", "genre_ids", "id"),
        ("novel", required_files["novel"], "genre_2", "genre_ids", "id"),
        ("episode", required_files["episode"], "novel_id", "novel_ids", "id"),
        ("comment", required_files["comment"], "novel_id", "novel_ids", "id"),
        ("comment", required_files["comment"], "episode_id", "episode_ids", "id"),
        ("novel_tag", required_files["novel_tag"], "novel_id", "novel_ids", "id"),
        ("novel_tag", required_files["novel_tag"], "tag_id", "tag_ids", "id"),
        ("novel_statistics", required_files["novel_statistics"], "novel_id", "novel_ids", "id"),
    ]
    for table, path, fk_col, ref_table, ref_col in fk_specs:
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row_no, row in enumerate(csv.DictReader(f), start=2):
                value = str(row.get(fk_col) or "").strip()
                if not value:
                    continue
                exists = con.execute(
                    f"SELECT 1 FROM {ref_table} WHERE {ref_col}=? LIMIT 1",
                    (value,),
                ).fetchone()
                if not exists:
                    orphan_rows.append({
                        "table_name": table,
                        "row_number": row_no,
                        "fk_column": fk_col,
                        "fk_value": value,
                        "referenced_table": ref_table,
                    })

    # 댓글 수 검증
    actual_counts = {
        row[0]: row[1]
        for row in con.execute(
            "SELECT episode_id, COUNT(*) FROM comment_ids GROUP BY episode_id"
        )
    }
    mismatch_rows: list[dict[str, Any]] = []
    with required_files["episode"].open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:
        for row in csv.DictReader(f):
            if str(row.get("access_type") or "").upper() != "FREE":
                continue
            episode_id = to_int(row.get("episode_id"), -1)
            declared = max(to_int(row.get("comment_count"), 0), 0)
            actual = actual_counts.get(episode_id, 0)
            if declared != actual:
                mismatch_rows.append({
                    "novel_id": row.get("novel_id", ""),
                    "episode_id": episode_id,
                    "episode_number": row.get("episode_number", ""),
                    "declared_comment_count": declared,
                    "actual_comment_count": actual,
                    "difference": actual - declared,
                    "comment_crawl_status": row.get("comment_crawl_status", ""),
                })

    with duplicate_report.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["table_name", "key_column", "duplicate_key"]
        )
        writer.writeheader()
        writer.writerows(dup_rows)

    with orphan_report.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "table_name", "row_number", "fk_column",
                "fk_value", "referenced_table",
            ],
        )
        writer.writeheader()
        writer.writerows(orphan_rows)

    with comment_report.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "novel_id", "episode_id", "episode_number",
                "declared_comment_count", "actual_comment_count",
                "difference", "comment_crawl_status",
            ],
        )
        writer.writeheader()
        writer.writerows(mismatch_rows)

    summary["duplicate_primary_keys"] = len(dup_rows)
    summary["orphan_foreign_keys"] = len(orphan_rows)
    summary["comment_count_mismatches"] = len(mismatch_rows)

    if dup_rows:
        summary["errors"].append(f"중복 PK {len(dup_rows)}건")
    if orphan_rows:
        summary["errors"].append(f"FK 고아 {len(orphan_rows)}건")
    if mismatch_rows:
        summary["warnings"].append(
            f"무료 회차 댓글 수 불일치 {len(mismatch_rows)}건"
        )

    summary["validation_passed"] = not summary["errors"]

    summary_path = VALIDATION_DIR / "validation_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    con.close()
    db_path.unlink(missing_ok=True)
    return summary


async def main() -> None:
    target_ids = load_existing_novel_ids(SOURCE_ID_CSV)

    if MAX_TARGETS is not None:
        target_ids = target_ids[:MAX_TARGETS]
        print(f"🧪 테스트 제한 적용: 앞 {len(target_ids):,}개 작품")

    if not target_ids:
        raise RuntimeError(
            f"처리할 작품 ID가 없습니다: {SOURCE_ID_CSV}"
        )

    manager = ERDCSVManager(
        DATA_DIR,
        AUDIT_DIR,
        target_ids,
    )
    crawler = MunpiaCrawler(
        manager,
        target_ids,
    )

    if not crawler.cookies:
        print(
            f"⚠️ 문피아 쿠키 없음 | {ENV_PATH}의 "
            f"MUNPIA_COOKIE를 확인하세요.",
            flush=True,
        )
    await crawler.run()

    if RUN_VALIDATION_ON_FINISH:
        print("\n🔎 전체 CSV 검증 시작")
        summary = validate_outputs(DATA_DIR)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ 수동 중단")
