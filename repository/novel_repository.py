from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import pandas as pd

from entity.comment import Comment
from entity.episode import Episode
from entity.novel import Novel
from entity.novel_author import NovelAuthor
from entity.novel_statistics import NovelStatistics
from service.novel_service_errors import CsvFileError, CsvSchemaError

NOVEL_REQUIRED_COLUMNS = {"work_id", "source_url", "title", "introduction", "origin_cover_url", "author_id", "free", "paid_serial", "exclusive", "pre_exclusive", "adult", "contest", "rental", "pause", "finish", "epub", "ebook", "cp_novel", "created_at", "updated_at", "paid_conversion_open_at", "isbn", "period", "unit_type", "collected_at"}
STATISTICS_REQUIRED_COLUMNS = {"work_id", "view_count", "preference_count", "like_count", "chapter_count", "free_chapter_count", "characters", "male_count", "female_count", "age_10s_percent", "age_20s_percent", "age_30s_percent", "age_40s_percent", "age_50s_percent", "notice_count", "collected_at"}
AUTHOR_REQUIRED_COLUMNS = {"author_id", "author_name", "author_url", "is_illustrator"}
EPISODE_REQUIRED_COLUMNS = {"work_id", "episode_id", "episode_number", "episode_title", "published_at", "access_type", "view_count", "like_count", "comment_count", "page_count", "adult", "paid_conversion_before_entry", "up", "collected_at"}
COMMENT_REQUIRED_COLUMNS = {"work_id", "episode_id", "comment_id", "parent_comment_id", "reply_level", "content_type", "comment_text", "like_count", "dislike_count", "created_at", "secret", "report_status", "block_status", "collected_at"}

class NovelRepository(ABC):
    """데이터 조회 계약(인터페이스)"""
    @abstractmethod
    def get_novel(self, novel_id: int) -> Novel | None: pass
    @abstractmethod
    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None: pass
    @abstractmethod
    def get_author(self, novel_id: int) -> NovelAuthor | None: pass
    @abstractmethod
    def get_episodes(self, novel_id: int) -> list[Episode]: pass
    @abstractmethod
    def get_comments(self, novel_id: int) -> list[Comment]: pass

class CsvNovelRepository(NovelRepository):
    """CSV 데이터를 다루는 DAO 구현체"""
    def __init__(
        self,
        works_csv_path: str | Path,
        authors_csv_path: str | Path,
        episodes_csv_path: str | Path,
        comments_csv_path: str | Path,
        *,
        works_chunk_size: int = 50_000,
        child_chunk_size: int = 500_000,
    ) -> None:
        self.works_csv_path = Path(works_csv_path)
        self.authors_csv_path = Path(authors_csv_path)
        self.episodes_csv_path = Path(episodes_csv_path)
        self.comments_csv_path = Path(comments_csv_path)
        
        self.works_chunk_size = works_chunk_size
        self.child_chunk_size = child_chunk_size

        self._work_row_cache: dict[int, pd.Series | None] = {}
        self._author_cache: dict[int, NovelAuthor | None] = {}
        self._episode_cache: dict[int, list[Episode]] = {}
        self._comment_cache: dict[int, list[Comment]] = {}

    def get_novel(self, novel_id: int) -> Novel | None:
        row = self._find_work_row(novel_id)
        if row is None:
            return None
        self._validate_columns(row.index, NOVEL_REQUIRED_COLUMNS, "works.csv")
        return self._row_to_novel(row)

    def get_novel_statistics(self, novel_id: int) -> NovelStatistics | None:
        row = self._find_work_row(novel_id)
        if row is None:
            return None
        self._validate_columns(row.index, STATISTICS_REQUIRED_COLUMNS, "works.csv")
        return self._row_to_novel_statistics(row)

    def get_author(self, novel_id: int) -> NovelAuthor | None:
        novel = self.get_novel(novel_id)
        if novel is None or novel.author_id is None:
            return None
        
        author_id = novel.author_id
        if author_id in self._author_cache:
            return self._author_cache[author_id]
        
        self._ensure_csv_file(self.authors_csv_path)
        self._validate_csv_header(self.authors_csv_path, AUTHOR_REQUIRED_COLUMNS, "authors.csv")
        
        try:
            rows = pd.read_csv(self.authors_csv_path, usecols=sorted(AUTHOR_REQUIRED_COLUMNS), dtype={"author_id": "int64"}, engine="c", low_memory=False, memory_map=True)
        except pd.errors.EmptyDataError:
            self._author_cache[author_id] = None
            return None
        except OSError as exc:
            raise CsvFileError(f"authors.csv를 읽을 수 없습니다: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"authors.csv 처리 중 오류가 발생했습니다: {exc}") from exc
            
        matched_rows = rows[rows["author_id"] == author_id]
        if matched_rows.empty:
            self._author_cache[author_id] = None
            return None
            
        author = self._row_to_author(matched_rows.iloc[0])
        self._author_cache[author_id] = author
        return author

    def get_episodes(self, novel_id: int) -> list[Episode]:
        if novel_id in self._episode_cache:
            return self._episode_cache[novel_id]
        rows = self._read_rows_by_work_id(self.episodes_csv_path, EPISODE_REQUIRED_COLUMNS, novel_id, "episodes.csv")
        if rows.empty:
            self._episode_cache[novel_id] = []
            return []
        episodes = self._rows_to_episodes(rows)
        episodes.sort(key=lambda episode: episode.episode_number)
        self._episode_cache[novel_id] = episodes
        return episodes

    def get_comments(self, novel_id: int) -> list[Comment]:
        if novel_id in self._comment_cache:
            return self._comment_cache[novel_id]
        rows = self._read_rows_by_work_id(self.comments_csv_path, COMMENT_REQUIRED_COLUMNS, novel_id, "comments.csv")
        if rows.empty:
            self._comment_cache[novel_id] = []
            return []
        comments = self._rows_to_comments(rows)
        self._comment_cache[novel_id] = comments
        return comments

    def _find_work_row(self, novel_id: int) -> pd.Series | None:
        if novel_id in self._work_row_cache:
            return self._work_row_cache[novel_id]
        self._ensure_csv_file(self.works_csv_path)
        try:
            for chunk in pd.read_csv(self.works_csv_path, chunksize=self.works_chunk_size, engine="c", low_memory=False, memory_map=True):
                if "work_id" not in chunk.columns:
                    raise CsvSchemaError("works.csv 필수 컬럼 누락: work_id")
                numeric_work_ids = pd.to_numeric(chunk["work_id"], errors="coerce")
                matched_rows = chunk[numeric_work_ids == novel_id]
                if not matched_rows.empty:
                    row = matched_rows.iloc[0].copy()
                    self._work_row_cache[novel_id] = row
                    return row
        except pd.errors.EmptyDataError as exc:
            raise CsvFileError(f"CSV 파일이 비어 있습니다: {self.works_csv_path}") from exc
        except CsvSchemaError:
            raise
        except OSError as exc:
            raise CsvFileError(f"works.csv를 읽을 수 없습니다: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"works.csv 처리 중 오류가 발생했습니다: {exc}") from exc
        self._work_row_cache[novel_id] = None
        return None

    def _read_rows_by_work_id(self, csv_path: Path, columns: set[str], novel_id: int, csv_name: str) -> pd.DataFrame:
        self._ensure_csv_file(csv_path)
        self._validate_csv_header(csv_path, columns, csv_name)
        matched_chunks = []
        try:
            for chunk in pd.read_csv(csv_path, usecols=sorted(columns), dtype={"work_id": "int64"}, chunksize=self.child_chunk_size, engine="c", low_memory=False, memory_map=True):
                if chunk.empty:
                    continue
                work_ids = chunk["work_id"]
                matched_rows = chunk[work_ids == novel_id]
                if not matched_rows.empty:
                    matched_chunks.append(matched_rows.copy())
        except pd.errors.EmptyDataError as exc:
            raise CsvFileError(f"CSV 파일이 비어 있습니다: {csv_path}") from exc
        except OSError as exc:
            raise CsvFileError(f"{csv_name}을 읽을 수 없습니다: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"{csv_name} 처리 중 오류가 발생했습니다: {exc}") from exc
        if not matched_chunks:
            return pd.DataFrame(columns=sorted(columns))
        return pd.concat(matched_chunks, ignore_index=True)

    def _ensure_csv_file(self, path: Path) -> None:
        if not path.exists():
            raise CsvFileError(f"CSV 파일을 찾을 수 없습니다: {path}")
        if not path.is_file():
            raise CsvFileError(f"올바른 파일 경로가 아닙니다: {path}")
        if path.stat().st_size == 0:
            raise CsvFileError(f"CSV 파일이 비어 있습니다: {path}")

    def _validate_csv_header(self, path: Path, required_columns: set[str], csv_name: str) -> None:
        try:
            header = pd.read_csv(path, nrows=0)
        except pd.errors.EmptyDataError as exc:
            raise CsvFileError(f"CSV 파일이 비어 있습니다: {path}") from exc
        except OSError as exc:
            raise CsvFileError(f"CSV 파일을 읽을 수 없습니다: {path}: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"{csv_name} 헤더 처리 중 오류가 발생했습니다: {exc}") from exc
        self._validate_columns(header.columns, required_columns, csv_name)

    def _validate_columns(self, columns: Any, required_columns: set[str], csv_name: str) -> None:
        missing = required_columns - set(columns)
        if missing:
            raise CsvSchemaError(f"{csv_name} 필수 컬럼 누락: {', '.join(sorted(missing))}")

    def _row_to_novel(self, row: pd.Series) -> Novel:
        try:
            return Novel(
                novel_id=int(row["work_id"]),
                source_url=self._required_str(row["source_url"], "source_url"),
                title=self._required_str(row["title"], "title"),
                introduction=self._optional_str(row["introduction"]),
                author_id=self._optional_int(row["author_id"]),
                illustrator_id=self._optional_int(row.get("illustrator_id")),
                origin_cover_url=self._optional_str(row["origin_cover_url"]),
                group_id=self._optional_int(row.get("group_id")),
                free=self._optional_bool(row["free"]),
                paid_serial=self._optional_bool(row["paid_serial"]),
                exclusive=self._optional_bool(row["exclusive"]),
                pre_exclusive=self._optional_bool(row["pre_exclusive"]),
                adult=self._optional_bool(row["adult"]),
                contest=self._optional_bool(row["contest"]),
                rental=self._optional_bool(row["rental"]),
                pause=self._optional_bool(row["pause"]),
                finish=self._optional_bool(row["finish"]),
                epub=self._optional_bool(row["epub"]),
                ebook=self._optional_bool(row["ebook"]),
                cp_novel=self._optional_bool(row["cp_novel"]),
                created_at=self._optional_datetime(row["created_at"]),
                updated_at=self._optional_datetime(row["updated_at"]),
                paid_conversion_open_at=self._optional_datetime(row["paid_conversion_open_at"]),
                isbn=self._optional_str(row["isbn"]),
                period=self._optional_int(row["period"]),
                unit_type=self._optional_str(row["unit_type"]),
                collected_at=self._optional_datetime(row["collected_at"]),
                genre_1=self._optional_int(row.get("genre_1")),
                genre_2=self._optional_int(row.get("genre_2")),
            )
        except CsvSchemaError:
            raise
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"Novel 변환에 실패했습니다: {exc}") from exc

    def _row_to_novel_statistics(self, row: pd.Series) -> NovelStatistics:
        try:
            return NovelStatistics(
                novel_id=int(row["work_id"]),
                view_count=self._optional_int(row["view_count"]),
                preference_count=self._optional_int(row["preference_count"]),
                like_count=self._optional_int(row["like_count"]),
                chapter_count=self._optional_int(row["chapter_count"]),
                free_chapter_count=self._optional_int(row["free_chapter_count"]),
                characters=self._optional_int(row["characters"]),
                male_count=self._optional_int(row["male_count"]),
                female_count=self._optional_int(row["female_count"]),
                age_10s_percent=self._optional_float(row["age_10s_percent"]),
                age_20s_percent=self._optional_float(row["age_20s_percent"]),
                age_30s_percent=self._optional_float(row["age_30s_percent"]),
                age_40s_percent=self._optional_float(row["age_40s_percent"]),
                age_50s_percent=self._optional_float(row["age_50s_percent"]),
                source_notice_count=self._optional_int(row["notice_count"]),
                collected_at=self._optional_datetime(row["collected_at"]),
            )
        except CsvSchemaError:
            raise
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"NovelStatistics 변환에 실패했습니다: {exc}") from exc

    def _row_to_author(self, row: pd.Series) -> NovelAuthor:
        try:
            is_illustrator = self._optional_bool(row["is_illustrator"])
            if is_illustrator is None:
                raise CsvSchemaError("authors.csv의 is_illustrator 값이 비어 있습니다.")
            return NovelAuthor(
                author_id=int(row["author_id"]),
                author_name=self._required_str(row["author_name"], "author_name"),
                author_url=self._optional_str(row["author_url"]),
                is_illustrator=is_illustrator,
            )
        except CsvSchemaError:
            raise
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"NovelAuthor 변환에 실패했습니다: {exc}") from exc

    def _rows_to_episodes(self, rows: pd.DataFrame) -> list[Episode]:
        episodes = []
        try:
            for row in rows.itertuples(index=False):
                episodes.append(Episode(
                    episode_id=int(row.episode_id), novel_id=int(row.work_id),
                    episode_number=int(row.episode_number),
                    episode_title=self._optional_str(row.episode_title),
                    published_at=self._optional_datetime(row.published_at),
                    access_type=self._optional_str(row.access_type),
                    view_count=self._optional_int(row.view_count),
                    like_count=self._optional_int(row.like_count),
                    comment_count=self._optional_int(row.comment_count),
                    page_count=self._optional_int(row.page_count),
                    adult=self._optional_bool(row.adult),
                    paid_conversion_before_entry=self._optional_bool(row.paid_conversion_before_entry),
                    up=self._optional_bool(row.up),
                    collected_at=self._optional_datetime(row.collected_at),
                ))
        except CsvSchemaError:
            raise
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"Episode 변환에 실패했습니다: {exc}") from exc
        return episodes

    def _rows_to_comments(self, rows: pd.DataFrame) -> list[Comment]:
        comments = []
        try:
            for row in rows.itertuples(index=False):
                comments.append(Comment(
                    comment_id=int(row.comment_id), novel_id=int(row.work_id),
                    episode_id=int(row.episode_id),
                    parent_comment_id=self._optional_int(row.parent_comment_id),
                    reply_level=self._optional_int(row.reply_level),
                    content_type=self._optional_str(row.content_type),
                    comment_text=self._optional_str(row.comment_text),
                    like_count=self._optional_int(row.like_count),
                    dislike_count=self._optional_int(row.dislike_count),
                    created_at=self._optional_datetime(row.created_at),
                    secret=self._optional_bool(row.secret),
                    report_status=self._optional_str(row.report_status),
                    block_status=self._optional_bool(row.block_status),
                    collected_at=self._optional_datetime(row.collected_at),
                ))
        except CsvSchemaError:
            raise
        except (ValueError, TypeError) as exc:
            raise CsvSchemaError(f"Comment 변환에 실패했습니다: {exc}") from exc
        return comments

    def _required_str(self, value: Any, column_name: str) -> str:
        if value is None or pd.isna(value):
            raise CsvSchemaError(f"필수 값이 비어 있습니다: {column_name}")
        result = str(value).strip()
        if not result:
            raise CsvSchemaError(f"필수 값이 비어 있습니다: {column_name}")
        return result

    def _optional_int(self, value: Any) -> int | None:
        if value is None or pd.isna(value):
            return None
        return int(float(value))

    def _optional_float(self, value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    def _optional_str(self, value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        return str(value).strip() or None

    def _optional_datetime(self, value: Any):
        if value is None or pd.isna(value):
            return None
        return pd.to_datetime(value, errors="raise").to_pydatetime()

    def _optional_bool(self, value: Any) -> bool | None:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "y", "yes"}:
            return True
        if normalized in {"false", "0", "n", "no"}:
            return False
        raise CsvSchemaError(f"boolean 값으로 변환할 수 없습니다: {value}")
