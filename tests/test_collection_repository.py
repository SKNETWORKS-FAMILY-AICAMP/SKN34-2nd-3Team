from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import csv
import multiprocessing
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from entity import Comment, Episode, Novel, NovelAuthor, NovelStatistics
from repository.collection_repository import CsvCollectionRepository
from repository.novel_repository import (
    AUTHOR_REQUIRED_COLUMNS,
    COMMENT_REQUIRED_COLUMNS,
    EPISODE_REQUIRED_COLUMNS,
    NOVEL_REQUIRED_COLUMNS,
    STATISTICS_REQUIRED_COLUMNS,
    CsvNovelRepository,
)
from service.novel_service_errors import CsvFileError, CsvSchemaError


def write_csv(path, headers, rows=()):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def csv_paths(tmp_path):
    paths = {name: tmp_path / f"{name}.csv" for name in ("works", "authors", "episodes", "comments")}
    write_csv(paths["works"], sorted(NOVEL_REQUIRED_COLUMNS | STATISTICS_REQUIRED_COLUMNS))
    write_csv(paths["authors"], sorted(AUTHOR_REQUIRED_COLUMNS))
    write_csv(paths["episodes"], sorted(EPISODE_REQUIRED_COLUMNS | {"source_url"}))
    write_csv(paths["comments"], sorted(COMMENT_REQUIRED_COLUMNS))
    return paths


def entities(title="첫 제목"):
    now = datetime(2026, 8, 3, 12, 0, 0)
    novel = Novel(123, "https://www.munpia.com/novel/detail/123", title, author_id=10, free=True, collected_at=now)
    statistics = NovelStatistics(123, view_count=100, chapter_count=1, free_chapter_count=1, collected_at=now)
    author = NovelAuthor(10, "작가", "https://library.munpia.com/author", False)
    episodes = [Episode(101, 123, 1, episode_title="1화", access_type="FREE", collected_at=now)]
    comments = [Comment(201, 123, 101, comment_text="댓글", collected_at=now)]
    return novel, statistics, author, episodes, comments


def repository(paths, **kwargs):
    return CsvCollectionRepository(
        paths["works"], paths["authors"], paths["episodes"], paths["comments"], **kwargs
    )


def read_repository(paths):
    return CsvNovelRepository(
        paths["works"], paths["authors"], paths["episodes"], paths["comments"]
    )


def test_save_can_be_read_immediately_by_fresh_novel_repository(csv_paths) -> None:
    repository(csv_paths).save_collection(*entities())
    reader = read_repository(csv_paths)
    assert reader.get_novel(123).title == "첫 제목"
    assert reader.get_novel_statistics(123).view_count == 100
    assert reader.get_author(123).author_name == "작가"
    assert [item.episode_id for item in reader.get_episodes(123)] == [101]
    assert [item.comment_id for item in reader.get_comments(123)] == [201]


def test_missing_csvs_are_bootstrapped_and_readable(tmp_path) -> None:
    paths = {
        name: tmp_path / "new" / f"{name}.csv"
        for name in ("works", "authors", "episodes", "comments")
    }

    repository(paths).save_collection(*entities())

    assert read_repository(paths).get_novel(123).title == "첫 제목"
    assert len(read_repository(paths).get_episodes(123)) == 1
    assert len(read_repository(paths).get_comments(123)) == 1


def test_existing_extra_columns_and_unrelated_rows_survive_streaming(csv_paths) -> None:
    headers = sorted(NOVEL_REQUIRED_COLUMNS | STATISTICS_REQUIRED_COLUMNS) + ["future_column"]
    rows = [
        {"work_id": number, "source_url": f"https://example/{number}", "title": f"작품 {number}", "future_column": f"keep-{number}"}
        for number in range(1000, 3000)
    ]
    write_csv(csv_paths["works"], headers, rows)

    repository(csv_paths).save_collection(*entities())

    with csv_paths["works"].open(encoding="utf-8-sig", newline="") as file:
        saved = list(csv.DictReader(file))
    assert len(saved) == 2001
    assert saved[0]["future_column"] == "keep-1000"
    assert saved[-2]["future_column"] == "keep-2999"
    assert saved[-1]["work_id"] == "123"


def test_existing_invalid_schema_is_rejected_without_touching_other_files(csv_paths) -> None:
    before = {name: path.read_bytes() for name, path in csv_paths.items()}
    write_csv(csv_paths["episodes"], ["work_id"])
    invalid_before = csv_paths["episodes"].read_bytes()

    with pytest.raises(CsvSchemaError, match="episodes.csv 필수 컬럼 누락"):
        repository(csv_paths).save_collection(*entities())

    assert csv_paths["episodes"].read_bytes() == invalid_before
    assert all(csv_paths[name].read_bytes() == data for name, data in before.items() if name != "episodes")


def test_fresh_reader_finds_collected_rows_in_unordered_csv(csv_paths) -> None:
    write_csv(
        csv_paths["comments"],
        sorted(COMMENT_REQUIRED_COLUMNS),
        [{"work_id": 999, "episode_id": 9991, "comment_id": 9992}],
    )
    repository(csv_paths).save_collection(*entities())
    assert [item.comment_id for item in read_repository(csv_paths).get_comments(123)] == [201]


def test_recollection_upserts_without_duplicate_primary_keys(csv_paths) -> None:
    writer = repository(csv_paths)
    writer.save_collection(*entities())
    writer.save_collection(*entities("갱신 제목"))

    for name, key in (("works", "work_id"), ("authors", "author_id"), ("episodes", "episode_id"), ("comments", "comment_id")):
        with csv_paths[name].open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 1
        assert len({row[key] for row in rows}) == 1
    assert read_repository(csv_paths).get_novel(123).title == "갱신 제목"


def test_replace_failure_rolls_back_all_four_files(csv_paths) -> None:
    repository(csv_paths).save_collection(*entities("기존 제목"))
    before = {name: path.read_bytes() for name, path in csv_paths.items()}
    calls = 0

    def fail_second_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        os.replace(source, target)

    with pytest.raises(CsvFileError, match="injected replacement failure"):
        repository(csv_paths, replace=fail_second_replace).save_collection(*entities())
    assert {name: path.read_bytes() for name, path in csv_paths.items()} == before


def test_replace_failure_removes_new_files_and_restores_existing_file(tmp_path) -> None:
    paths = {name: tmp_path / f"{name}.csv" for name in ("works", "authors", "episodes", "comments")}
    write_csv(
        paths["works"],
        sorted(NOVEL_REQUIRED_COLUMNS | STATISTICS_REQUIRED_COLUMNS),
        [{"work_id": 123, "title": "기존 제목", "source_url": "https://example/123"}],
    )
    before = paths["works"].read_bytes()
    calls = 0

    def fail_second_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected mixed replacement failure")
        os.replace(source, target)

    with pytest.raises(CsvFileError, match="mixed replacement failure"):
        repository(paths, replace=fail_second_replace).save_collection(*entities())

    assert paths["works"].read_bytes() == before
    assert all(not paths[name].exists() for name in ("authors", "episodes", "comments"))


def test_new_work_fast_path_does_not_search_existing_episode_or_comment_rows(
    csv_paths
) -> None:
    writer = repository(csv_paths)
    searched = []
    original_find_row = writer._find_row

    def tracked_find_row(path, key, value):
        searched.append(path)
        return original_find_row(path, key, value)

    writer._find_row = tracked_find_row
    writer.save_collection(*entities())

    assert searched == [csv_paths["works"], csv_paths["authors"]]


def test_append_failure_truncates_all_existing_files(csv_paths) -> None:
    before = {name: path.read_bytes() for name, path in csv_paths.items()}
    calls = 0

    def fail_second_append(path, rows, headers):
        nonlocal calls
        calls += 1
        CsvCollectionRepository._append_rows(repository(csv_paths), path, rows, headers)
        if calls == 2:
            raise OSError("injected append failure")

    writer = repository(csv_paths)
    writer._append_rows = fail_second_append
    with pytest.raises(CsvFileError, match="injected append failure"):
        writer.save_collection(*entities())

    assert {name: path.read_bytes() for name, path in csv_paths.items()} == before


def _save_title(paths: dict[str, str], work_id: int, title: str) -> None:
    concrete = {name: Path(path) for name, path in paths.items()}
    novel, statistics, author, episodes, comments = entities(title)
    novel = replace(novel, novel_id=work_id, author_id=work_id)
    statistics = replace(statistics, novel_id=work_id)
    author = replace(author, author_id=work_id)
    episodes = [replace(episodes[0], novel_id=work_id, episode_id=work_id * 10 + 1)]
    comments = [
        replace(
            comments[0],
            novel_id=work_id,
            episode_id=episodes[0].episode_id,
            comment_id=work_id * 10 + 2,
        )
    ]
    repository(concrete).save_collection(novel, statistics, author, episodes, comments)


def test_multiprocess_saves_are_serialized_without_lost_rows(csv_paths) -> None:
    string_paths = {name: str(path) for name, path in csv_paths.items()}
    processes = [
        multiprocessing.Process(target=_save_title, args=(string_paths, work_id, title))
        for work_id, title in ((123, "첫 작품"), (456, "둘째 작품"))
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0

    with csv_paths["works"].open(encoding="utf-8-sig", newline="") as file:
        assert {row["work_id"] for row in csv.DictReader(file)} == {"123", "456"}


def test_same_process_saves_are_serialized_without_lost_rows(csv_paths) -> None:
    string_paths = {name: str(path) for name, path in csv_paths.items()}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_save_title, string_paths, work_id, title)
            for work_id, title in ((123, "첫 작품"), (456, "둘째 작품"))
        ]
        for future in futures:
            future.result(timeout=10)

    with csv_paths["works"].open(encoding="utf-8-sig", newline="") as file:
        assert {row["work_id"] for row in csv.DictReader(file)} == {"123", "456"}


def test_failed_rollback_keeps_only_recovery_backup_and_reports_its_path(
    csv_paths, monkeypatch
) -> None:
    writer = repository(csv_paths)
    writer.save_collection(*entities("기존 제목"))
    real_replace = os.replace
    replacement_calls = 0

    def fail_commit(source, target):
        nonlocal replacement_calls
        replacement_calls += 1
        if replacement_calls == 2:
            raise OSError("commit failed")
        real_replace(source, target)

    writer._replace = fail_commit

    def fail_works_restore(source, target):
        if ".backup-" in str(source) and Path(target) == csv_paths["works"]:
            raise OSError("restore failed")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_works_restore)
    with pytest.raises(CsvFileError, match=r"rollback.*backup.*works\.csv\.backup"):
        writer.save_collection(*entities())

    backups = list(csv_paths["works"].parent.glob(".works.csv.backup-*"))
    assert len(backups) == 1


def test_recollection_preserves_target_extra_columns_by_primary_key(csv_paths) -> None:
    writer = repository(csv_paths)
    writer.save_collection(*entities())
    for name, key in (
        ("works", "work_id"),
        ("authors", "author_id"),
        ("episodes", "episode_id"),
        ("comments", "comment_id"),
    ):
        with csv_paths[name].open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
            headers = list(rows[0]) + ["future_column"]
        rows[0]["future_column"] = f"keep-{name}"
        write_csv(csv_paths[name], headers, rows)

    writer.save_collection(*entities("갱신 제목"))

    for name in csv_paths:
        with csv_paths[name].open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        assert rows[0]["future_column"] == f"keep-{name}"
