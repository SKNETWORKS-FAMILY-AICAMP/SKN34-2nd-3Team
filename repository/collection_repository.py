from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
import csv
import fcntl
import os
import tempfile
import threading

from entity import Comment, Episode, Novel, NovelAuthor, NovelStatistics
from repository.novel_repository import (
    AUTHOR_REQUIRED_COLUMNS,
    COMMENT_REQUIRED_COLUMNS,
    EPISODE_REQUIRED_COLUMNS,
    NOVEL_REQUIRED_COLUMNS,
    STATISTICS_REQUIRED_COLUMNS,
)
from service.novel_service_errors import CsvFileError, CsvSchemaError


_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


class CollectionRepository(ABC):
    """수집된 Entity 묶음을 영속화하는 저장 계약."""

    @abstractmethod
    def save_collection(
        self,
        novel: Novel,
        statistics: NovelStatistics,
        author: NovelAuthor | None,
        episodes: list[Episode],
        comments: list[Comment],
    ) -> None:
        pass


class CsvCollectionRepository(CollectionRepository):
    """대형 CSV를 스트리밍하고 네 파일을 한 트랜잭션처럼 교체한다."""

    REQUIRED_COLUMNS = {
        "works": NOVEL_REQUIRED_COLUMNS | STATISTICS_REQUIRED_COLUMNS,
        "authors": AUTHOR_REQUIRED_COLUMNS,
        "episodes": EPISODE_REQUIRED_COLUMNS,
        "comments": COMMENT_REQUIRED_COLUMNS,
    }

    def __init__(
        self,
        works_csv_path: str | Path,
        authors_csv_path: str | Path,
        episodes_csv_path: str | Path,
        comments_csv_path: str | Path,
        *,
        replace: Callable[[str | Path, str | Path], None] = os.replace,
    ) -> None:
        self.paths = {
            "works": Path(works_csv_path),
            "authors": Path(authors_csv_path),
            "episodes": Path(episodes_csv_path),
            "comments": Path(comments_csv_path),
        }
        self._replace = replace

    def save_collection(
        self,
        novel: Novel,
        statistics: NovelStatistics,
        author: NovelAuthor | None,
        episodes: list[Episode],
        comments: list[Comment],
    ) -> None:
        self._validate_entities(novel, statistics, author, episodes, comments)
        with self._collection_lock():
            self._save_locked(novel, statistics, author, episodes, comments)

    def _save_locked(
        self,
        novel: Novel,
        statistics: NovelStatistics,
        author: NovelAuthor | None,
        episodes: list[Episode],
        comments: list[Comment],
    ) -> None:
        headers = self._validate_and_get_headers()
        new_rows = {
            "works": [self._novel_row(novel, statistics)],
            "authors": [asdict(author)] if author is not None else [],
            "episodes": [self._entity_row(item) for item in episodes],
            "comments": [self._entity_row(item) for item in comments],
        }
        existing_work = self._find_row(self.paths["works"], "work_id", novel.novel_id)
        if existing_work is None:
            existing_author = (
                self._find_row(self.paths["authors"], "author_id", author.author_id)
                if author is not None
                else None
            )
            if existing_author is not None:
                new_rows["authors"] = []
            self._append_transaction(headers, new_rows)
            return

        old_author_id = existing_work.get("author_id")
        author_match = str(author.author_id) if author else old_author_id
        match_values = {
            "works": ("work_id", str(novel.novel_id)),
            "authors": ("author_id", author_match) if author_match else None,
            "episodes": ("work_id", str(novel.novel_id)),
            "comments": ("work_id", str(novel.novel_id)),
        }
        primary_keys = {
            "works": "work_id",
            "authors": "author_id",
            "episodes": "episode_id",
            "comments": "comment_id",
        }

        staging: dict[str, Path] = {}
        backups: dict[str, Path] = {}
        originally_present = {name: path.exists() for name, path in self.paths.items()}
        committed = False
        try:
            for name, path in self.paths.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                staging[name] = self._temporary_path(path, "stage")
                self._stream_stage(
                    path,
                    staging[name],
                    headers[name],
                    match_values[name],
                    new_rows[name],
                    primary_keys[name],
                )

            for name, path in self.paths.items():
                if originally_present[name]:
                    backup = self._temporary_path(path, "backup")
                    backup.unlink()
                    os.replace(path, backup)
                    backups[name] = backup
                self._replace(staging[name], path)
            committed = True
        except Exception as exc:
            rollback_errors = self._rollback(backups, originally_present)
            detail = (
                f" (rollback 실패, recovery backup: {'; '.join(rollback_errors)})"
                if rollback_errors
                else ""
            )
            raise CsvFileError(f"수집 CSV 저장에 실패했습니다: {exc}{detail}") from exc
        finally:
            cleanup = list(staging.values())
            if committed:
                cleanup.extend(backups.values())
            for path in cleanup:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    @contextmanager
    def _collection_lock(self):
        lock_path = self.paths["works"].with_name(".collection-save.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        key = str(lock_path.resolve())
        with _LOCKS_GUARD:
            process_lock = _PROCESS_LOCKS.setdefault(key, threading.RLock())
        with process_lock:
            try:
                with lock_path.open("a+") as lock_file:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                raise CsvFileError(f"수집 CSV 잠금에 실패했습니다: {exc}") from exc

    def _find_row(self, path: Path, key: str, value: Any) -> dict[str, str] | None:
        if not path.exists():
            return None
        expected = str(value)
        try:
            with path.open(encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    if row.get(key) == expected:
                        return row
        except OSError as exc:
            raise CsvFileError(f"{path.name}을 검색할 수 없습니다: {exc}") from exc
        return None

    def _append_transaction(
        self,
        headers: dict[str, list[str]],
        new_rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        original = {
            name: (path.exists(), path.stat().st_size if path.exists() else 0)
            for name, path in self.paths.items()
        }
        try:
            for name, path in self.paths.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                self._append_rows(path, new_rows[name], headers[name])
        except Exception as exc:
            rollback_errors: list[str] = []
            for name, path in reversed(tuple(self.paths.items())):
                existed, size = original[name]
                try:
                    if existed:
                        with path.open("r+b") as file:
                            file.truncate(size)
                            file.flush()
                            os.fsync(file.fileno())
                    else:
                        path.unlink(missing_ok=True)
                except OSError as rollback_exc:
                    rollback_errors.append(f"{name} ({path}): {rollback_exc}")
            detail = f" (rollback 실패: {'; '.join(rollback_errors)})" if rollback_errors else ""
            raise CsvFileError(f"수집 CSV append에 실패했습니다: {exc}{detail}") from exc

    def _append_rows(
        self, path: Path, rows: Iterable[dict[str, Any]], headers: list[str]
    ) -> None:
        try:
            is_empty = not path.exists() or path.stat().st_size == 0
            with path.open("a", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=headers)
                if is_empty:
                    writer.writeheader()
                writer.writerows(self._fit_row(headers, row) for row in rows)
                file.flush()
                os.fsync(file.fileno())
        except OSError as exc:
            raise CsvFileError(f"{path.name}에 append할 수 없습니다: {exc}") from exc

    def _validate_and_get_headers(self) -> dict[str, list[str]]:
        headers: dict[str, list[str]] = {}
        for name, path in self.paths.items():
            if not path.exists():
                headers[name] = sorted(self.REQUIRED_COLUMNS[name])
                continue
            if not path.is_file():
                raise CsvFileError(f"올바른 파일 경로가 아닙니다: {path}")
            try:
                with path.open(encoding="utf-8-sig", newline="") as file:
                    fieldnames = csv.DictReader(file).fieldnames
            except OSError as exc:
                raise CsvFileError(f"{name}.csv을 읽을 수 없습니다: {exc}") from exc
            if not fieldnames:
                raise CsvSchemaError(f"{name}.csv 헤더가 없습니다.")
            missing = self.REQUIRED_COLUMNS[name] - set(fieldnames)
            if missing:
                raise CsvSchemaError(
                    f"{name}.csv 필수 컬럼 누락: {', '.join(sorted(missing))}"
                )
            headers[name] = list(fieldnames)
        return headers

    def _stream_stage(
        self,
        source: Path,
        destination: Path,
        headers: list[str],
        match: tuple[str, str] | None,
        new_rows: Iterable[dict[str, Any]],
        primary_key: str,
    ) -> None:
        try:
            preserved: dict[str, dict[str, str]] = {}
            with destination.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=headers)
                writer.writeheader()
                if source.exists():
                    with source.open(encoding="utf-8-sig", newline="") as input_file:
                        for row in csv.DictReader(input_file):
                            if match is not None and row.get(match[0]) == match[1]:
                                preserved[row.get(primary_key, "")] = row
                            else:
                                writer.writerow({header: row.get(header, "") for header in headers})
                for row in new_rows:
                    merged = dict(preserved.get(str(row.get(primary_key)), {}))
                    merged.update(row)
                    writer.writerow(self._fit_row(headers, merged))
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise CsvFileError(f"{source.name} staging 파일을 쓸 수 없습니다: {exc}") from exc

    def _temporary_path(self, target: Path, kind: str) -> Path:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.{kind}-", dir=target.parent
        )
        os.close(descriptor)
        return Path(name)

    def _rollback(
        self, backups: dict[str, Path], originally_present: dict[str, bool]
    ) -> list[str]:
        errors: list[str] = []
        for name, path in reversed(tuple(self.paths.items())):
            try:
                backup = backups.get(name)
                if backup is not None and backup.exists():
                    os.replace(backup, path)
                elif not originally_present[name]:
                    path.unlink(missing_ok=True)
            except OSError as exc:
                backup = backups.get(name)
                backup_detail = f"{backup}" if backup is not None else "없음"
                errors.append(f"{name} backup={backup_detail}: {exc}")
        return errors

    def _novel_row(
        self, novel: Novel, statistics: NovelStatistics
    ) -> dict[str, Any]:
        row = self._entity_row(novel)
        stat_row = self._entity_row(statistics)
        stat_row.pop("work_id")
        stat_row["notice_count"] = stat_row.pop("source_notice_count")
        row.update(stat_row)
        return row

    def _entity_row(self, entity: Any) -> dict[str, Any]:
        row = asdict(entity)
        if "novel_id" in row:
            row["work_id"] = row.pop("novel_id")
        return row

    def _fit_row(self, headers: list[str], values: dict[str, Any]) -> dict[str, str]:
        return {header: self._serialize(values.get(header)) for header in headers}

    def _serialize(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _validate_entities(
        self,
        novel: Novel,
        statistics: NovelStatistics,
        author: NovelAuthor | None,
        episodes: list[Episode],
        comments: list[Comment],
    ) -> None:
        if statistics.novel_id != novel.novel_id:
            raise CsvSchemaError("작품과 통계의 작품 ID가 일치하지 않습니다.")
        if any(item.novel_id != novel.novel_id for item in episodes + comments):
            raise CsvSchemaError("회차 또는 댓글의 작품 ID가 일치하지 않습니다.")
        episode_ids = {item.episode_id for item in episodes}
        if any(item.episode_id not in episode_ids for item in comments):
            raise CsvSchemaError("댓글이 수집 회차에 속하지 않습니다.")
        if author is not None and novel.author_id != author.author_id:
            raise CsvSchemaError("작품과 작가의 작가 ID가 일치하지 않습니다.")
