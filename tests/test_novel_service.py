from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from clawler.munpia_crawler import ALL_HEADERS
from service.novel_service import (
    CsvSchemaError,
    InvalidNovelInputError,
    NovelService,
)


def make_row(table: str, **values: Any) -> dict[str, str]:
    row = {column: "" for column in ALL_HEADERS[table]}
    row.update({key: str(value) for key, value in values.items()})
    return row


def write_table(
    data_dir: Path,
    table: str,
    rows: list[dict[str, Any]] | None = None,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{table}.csv"

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=ALL_HEADERS[table],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows or []:
            writer.writerow(make_row(table, **row))


def read_table(
    data_dir: Path,
    table: str,
) -> list[dict[str, str]]:
    with (data_dir / f"{table}.csv").open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


@pytest.fixture
def service(tmp_path: Path) -> NovelService:
    data_dir = tmp_path / "data"
    audit_dir = tmp_path / "audit"

    for table in ALL_HEADERS:
        write_table(data_dir, table)

    return NovelService(
        data_dir=data_dir,
        audit_dir=audit_dir,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("512551", 512551),
        (
            "https://www.munpia.com/novel/detail/512551",
            512551,
        ),
        ("https://novel.munpia.com/512551", 512551),
        (
            "https://example.test/path?novelId=512551",
            512551,
        ),
    ],
)
def test_extract_novel_id(
    value: str,
    expected: int,
) -> None:
    assert NovelService.extract_novel_id(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "   ", "https://example.test/no-id", "not-a-link"],
)
def test_extract_novel_id_rejects_invalid_input(
    value: str,
) -> None:
    with pytest.raises(InvalidNovelInputError):
        NovelService.extract_novel_id(value)


def test_list_novels_keeps_csv_order_and_paginates(
    service: NovelService,
) -> None:
    novels = [
        {
            "novel_id": number,
            "title": f"작품 {number}",
            "author_id": 10,
        }
        for number in range(1, 26)
    ]
    write_table(service.data_dir, "novel", novels)
    write_table(
        service.data_dir,
        "novel_author",
        [{
            "author_id": 10,
            "author_name": "테스트 작가",
        }],
    )
    write_table(
        service.data_dir,
        "novel_statistics",
        [
            {
                "novel_id": number,
                "view_count": number * 100,
            }
            for number in range(1, 26)
        ],
    )

    first = service.list_novels(page=1, page_size=20)
    second = service.list_novels(page=2, page_size=20)

    assert first.total_rows == 25
    assert first.total_pages == 2
    assert len(first.rows) == 20
    assert first.rows[0]["novel_id"] == "1"
    assert first.rows[-1]["novel_id"] == "20"
    assert first.rows[0]["author_name"] == "테스트 작가"
    assert first.rows[0]["view_count"] == "100"

    assert len(second.rows) == 5
    assert second.rows[0]["novel_id"] == "21"
    assert second.rows[-1]["novel_id"] == "25"


def test_invalid_csv_header_raises_schema_error(
    service: NovelService,
) -> None:
    path = service.data_dir / "novel.csv"
    path.write_text(
        "wrong_column\nvalue\n",
        encoding="utf-8-sig",
    )

    with pytest.raises(CsvSchemaError):
        service.list_novels()


def test_overwrite_replaces_scoped_rows_and_upserts_masters(
    service: NovelService,
) -> None:
    # Existing target rows and unrelated rows.
    write_table(
        service.data_dir,
        "novel",
        [
            {
                "novel_id": 512551,
                "title": "이전 제목",
                "author_id": 1,
            },
            {
                "novel_id": 999999,
                "title": "다른 작품",
                "author_id": 9,
            },
        ],
    )
    write_table(
        service.data_dir,
        "episode",
        [
            {
                "episode_id": 1,
                "novel_id": 512551,
                "episode_title": "이전 회차",
            },
            {
                "episode_id": 99,
                "novel_id": 999999,
                "episode_title": "보존 회차",
            },
        ],
    )
    write_table(
        service.data_dir,
        "comment",
        [
            {
                "comment_id": 1,
                "novel_id": 512551,
                "episode_id": 1,
                "comment_text": "이전 댓글",
            },
            {
                "comment_id": 99,
                "novel_id": 999999,
                "episode_id": 99,
                "comment_text": "보존 댓글",
            },
        ],
    )
    write_table(
        service.data_dir,
        "novel_author",
        [
            {
                "author_id": 1,
                "author_name": "이전 작가명",
            },
            {
                "author_id": 9,
                "author_name": "보존 작가",
            },
        ],
    )
    write_table(
        service.data_dir,
        "novel_ai_evaluation",
        [{
            "evaluation_id": 7,
            "novel_id": 512551,
            "evaluation_type": "summary",
        }],
    )

    evaluation_before = (
        service.data_dir / "novel_ai_evaluation.csv"
    ).read_bytes()

    result = {
        "novel_author": {
            "author_id": 1,
            "author_name": "최신 작가명",
        },
        "novel_group": [],
        "novel_genre": [],
        "tag": [],
        "novel_tag": [
            {
                "novel_id": 512551,
                "tag_id": 101,
            },
        ],
        "novel": {
            "novel_id": 512551,
            "title": "최신 제목",
            "author_id": 1,
        },
        "novel_statistics": {
            "novel_id": 512551,
            "view_count": 12345,
        },
        "episode": [
            {
                "episode_id": 2,
                "novel_id": 512551,
                "episode_number": 1,
                "episode_title": "최신 회차",
            },
        ],
        "comment": [
            {
                "comment_id": 2,
                "novel_id": 512551,
                "episode_id": 2,
                "comment_text": "최신 댓글",
            },
        ],
    }

    changed = service._overwrite_from_result(
        novel_id=512551,
        result=result,
    )

    novels = read_table(service.data_dir, "novel")
    episodes = read_table(service.data_dir, "episode")
    comments = read_table(service.data_dir, "comment")
    authors = read_table(service.data_dir, "novel_author")

    assert changed["novel"] == 1
    assert changed["episode"] == 1
    assert changed["comment"] == 1

    assert {
        row["novel_id"]: row["title"]
        for row in novels
    } == {
        "999999": "다른 작품",
        "512551": "최신 제목",
    }

    assert {
        row["episode_id"]: row["episode_title"]
        for row in episodes
    } == {
        "99": "보존 회차",
        "2": "최신 회차",
    }

    assert {
        row["comment_id"]: row["comment_text"]
        for row in comments
    } == {
        "99": "보존 댓글",
        "2": "최신 댓글",
    }

    assert {
        row["author_id"]: row["author_name"]
        for row in authors
    } == {
        "1": "최신 작가명",
        "9": "보존 작가",
    }

    assert (
        service.data_dir / "novel_ai_evaluation.csv"
    ).read_bytes() == evaluation_before


class FakeCrawler:
    def __init__(
        self,
        result: dict[str, Any],
    ) -> None:
        self.result = result
        self.active_states: dict[int, dict[str, Any]] = {}

    def collect_one_sync(
        self,
        novel_id: int,
    ) -> dict[str, Any]:
        return self.result


def successful_result(
    novel_id: int,
    title: str,
) -> dict[str, Any]:
    return {
        "type": "SUCCESS",
        "novel_author": {
            "author_id": 1,
            "author_name": "작가",
        },
        "novel_group": [],
        "novel_genre": [],
        "tag": [],
        "novel_tag": [],
        "novel": {
            "novel_id": novel_id,
            "title": title,
            "author_id": 1,
        },
        "novel_statistics": {
            "novel_id": novel_id,
        },
        "episode": [],
        "comment": [],
    }


def test_collect_or_update_reports_insert(
    service: NovelService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crawler = FakeCrawler(
        successful_result(512551, "신규 작품")
    )
    monkeypatch.setattr(
        service,
        "_create_crawler",
        lambda: crawler,
    )

    result = service.collect_or_update("512551")

    assert result.novel_id == 512551
    assert result.change_type == "INSERT"
    assert result.title == "신규 작품"


def test_collect_or_update_reports_update(
    service: NovelService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_table(
        service.data_dir,
        "novel",
        [{
            "novel_id": 512551,
            "title": "이전 작품",
        }],
    )

    crawler = FakeCrawler(
        successful_result(512551, "갱신 작품")
    )
    monkeypatch.setattr(
        service,
        "_create_crawler",
        lambda: crawler,
    )

    result = service.collect_or_update("512551")

    assert result.change_type == "UPDATE"

    novels = read_table(service.data_dir, "novel")
    assert len(novels) == 1
    assert novels[0]["title"] == "갱신 작품"


def test_parallel_progress_message_contains_counts() -> None:
    message = NovelService._progress_message({
        "phase": "EPISODE_PARALLEL",
        "chapter_done": 12,
        "chapter_total": 100,
        "chapter_in_flight": 20,
        "chapter_failed": 2,
    })

    assert "완료 12/100" in message
    assert "처리 중 20개" in message
    assert "실패 2개" in message
