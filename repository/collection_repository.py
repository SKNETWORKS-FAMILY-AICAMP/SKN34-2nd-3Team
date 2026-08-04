from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
import csv
import os
import tempfile
import threading

from clawler.munpia_crawler import ALL_HEADERS
from service.novel_service_errors import CsvFileError, CsvSchemaError

try:  # POSIX
    import fcntl  # type: ignore
except ImportError:  # Windows
    fcntl = None

try:  # Windows
    import msvcrt  # type: ignore
except ImportError:  # POSIX
    msvcrt = None


MASTER_TABLES = ("novel_author", "novel_group", "novel_genre", "tag")
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

_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _key(row: dict[str, Any], columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_text(row.get(column)).strip() for column in columns)


def _as_rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


class CollectionRepository(ABC):
    @abstractmethod
    def save_result(self, novel_id: int, result: dict[str, Any]) -> dict[str, int]:
        pass

    @abstractmethod
    def novel_exists(self, novel_id: int) -> bool:
        pass

    @abstractmethod
    def list_novels(self, page: int, page_size: int) -> tuple[list[dict[str, str]], int]:
        pass

    @abstractmethod
    def find_page(self, novel_id: int, page_size: int) -> int:
        pass


class CsvCollectionRepository(CollectionRepository):
    """ERD CSV를 작품 단위로 안전하게 갱신한다."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths = {
            table: self.data_dir / f"{table}.csv"
            for table in ALL_HEADERS
        }
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        for table, headers in ALL_HEADERS.items():
            path = self.paths[table]
            if not path.exists():
                with path.open("w", encoding="utf-8-sig", newline="") as file:
                    csv.writer(file).writerow(headers)
            self._validate_header(table)

    def _validate_header(self, table: str) -> None:
        path = self.paths[table]
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                actual = csv.DictReader(file).fieldnames or []
        except OSError as exc:
            raise CsvFileError(f"{path.name}을 읽을 수 없습니다: {exc}") from exc
        expected = ALL_HEADERS[table]
        if actual != expected:
            raise CsvSchemaError(
                f"{path.name} 헤더 불일치. 현재={actual}, 기대={expected}"
            )

    def novel_exists(self, novel_id: int) -> bool:
        return self._find_row(self.paths["novel"], "novel_id", novel_id) is not None

    def save_result(self, novel_id: int, result: dict[str, Any]) -> dict[str, int]:
        changed: dict[str, int] = {}
        with self._collection_lock():
            staged: dict[str, Path] = {}
            backups: dict[str, Path] = {}
            present = {table: path.exists() for table, path in self.paths.items()}
            try:
                for table in MASTER_TABLES + NOVEL_SCOPED_TABLES:
                    incoming = _as_rows(result.get(table))
                    changed[table] = len(incoming)
                    staged[table] = self._stage_table(
                        table=table,
                        novel_id=novel_id,
                        incoming=incoming,
                    )

                for table, stage_path in staged.items():
                    target = self.paths[table]
                    if target.exists():
                        backup = self._temporary_path(target, "backup")
                        backup.unlink(missing_ok=True)
                        os.replace(target, backup)
                        backups[table] = backup
                    os.replace(stage_path, target)
            except Exception as exc:
                for table, target in self.paths.items():
                    backup = backups.get(table)
                    try:
                        if backup and backup.exists():
                            os.replace(backup, target)
                        elif table in staged and not present[table]:
                            target.unlink(missing_ok=True)
                    except OSError:
                        pass
                if isinstance(exc, (CsvFileError, CsvSchemaError)):
                    raise
                raise CsvFileError(f"ERD CSV 저장에 실패했습니다: {exc}") from exc
            finally:
                for path in list(staged.values()) + list(backups.values()):
                    path.unlink(missing_ok=True)
        return changed

    def _stage_table(
        self,
        *,
        table: str,
        novel_id: int,
        incoming: list[dict[str, Any]],
    ) -> Path:
        source = self.paths[table]
        headers = ALL_HEADERS[table]
        temp = self._temporary_path(source, "stage")
        incoming_by_key = {
            _key(row, PRIMARY_KEYS[table]): row
            for row in incoming
            if all(_key(row, PRIMARY_KEYS[table]))
        }
        target_novel = str(novel_id)

        try:
            with temp.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                with source.open("r", encoding="utf-8-sig", newline="") as input_file:
                    for row in csv.DictReader(input_file):
                        if table in NOVEL_SCOPED_TABLES:
                            if row.get("novel_id") == target_novel:
                                continue
                            writer.writerow({column: row.get(column, "") for column in headers})
                            continue

                        row_key = _key(row, PRIMARY_KEYS[table])
                        replacement = incoming_by_key.pop(row_key, None)
                        writer.writerow(
                            self._fit(headers, replacement if replacement is not None else row)
                        )

                if table in NOVEL_SCOPED_TABLES:
                    for row in incoming:
                        writer.writerow(self._fit(headers, row))
                else:
                    for row in incoming_by_key.values():
                        writer.writerow(self._fit(headers, row))
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise CsvFileError(f"{source.name} staging 실패: {exc}") from exc
        return temp

    def list_novels(self, page: int, page_size: int) -> tuple[list[dict[str, str]], int]:
        if page_size <= 0:
            raise ValueError("page_size는 1 이상이어야 합니다.")
        page = max(1, int(page))

        authors: dict[str, str] = {}
        with self.paths["novel_author"].open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                authors[row.get("author_id", "")] = row.get("author_name", "")

        statistics: dict[str, dict[str, str]] = {}
        with self.paths["novel_statistics"].open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                statistics[row.get("novel_id", "")] = row

        start = (page - 1) * page_size
        end = start + page_size
        rows: list[dict[str, str]] = []
        total = 0
        with self.paths["novel"].open("r", encoding="utf-8-sig", newline="") as file:
            for novel in csv.DictReader(file):
                if start <= total < end:
                    novel_id = novel.get("novel_id", "")
                    stats = statistics.get(novel_id, {})
                    author_id = novel.get("author_id", "")
                    rows.append({
                        "novel_id": novel_id,
                        "title": novel.get("title", ""),
                        "author_name": novel.get("author_name", "") or authors.get(author_id, ""),
                        "free": novel.get("free", ""),
                        "paid_serial": novel.get("paid_serial", ""),
                        "finish": novel.get("finish", ""),
                        "view_count": stats.get("view_count", ""),
                        "preference_count": stats.get("preference_count", ""),
                        "chapter_count": stats.get("chapter_count", ""),
                        "collected_at": novel.get("collected_at", ""),
                        "crawl_status": novel.get("crawl_status", ""),
                    })
                total += 1
        return rows, total

    def find_page(self, novel_id: int, page_size: int) -> int:
        target = str(novel_id)
        with self.paths["novel"].open("r", encoding="utf-8-sig", newline="") as file:
            for index, row in enumerate(csv.DictReader(file)):
                if row.get("novel_id") == target:
                    return index // page_size + 1
        return 1

    @contextmanager
    def _collection_lock(self):
        lock_path = self.data_dir / ".collection-save.lock"
        key = str(lock_path.resolve())
        with _LOCKS_GUARD:
            process_lock = _PROCESS_LOCKS.setdefault(key, threading.RLock())
        with process_lock:
            try:
                with lock_path.open("a+b") as lock_file:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    elif msvcrt is not None:
                        lock_file.seek(0)
                        if lock_file.tell() == 0:
                            lock_file.write(b"0")
                            lock_file.flush()
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        yield
                    finally:
                        if fcntl is not None:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                        elif msvcrt is not None:
                            lock_file.seek(0)
                            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as exc:
                raise CsvFileError(f"CSV 잠금에 실패했습니다: {exc}") from exc

    def _find_row(self, path: Path, key: str, value: Any) -> dict[str, str] | None:
        expected = str(value)
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get(key) == expected:
                    return row
        return None

    @staticmethod
    def _fit(headers: list[str], row: dict[str, Any]) -> dict[str, str]:
        return {column: _text(row.get(column, "")) for column in headers}

    @staticmethod
    def _temporary_path(target: Path, kind: str) -> Path:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.{kind}-", dir=target.parent
        )
        os.close(descriptor)
        return Path(name)
